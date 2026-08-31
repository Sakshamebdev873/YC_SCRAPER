import pytest

from app.db import now_iso
from app.seed import seed_templates
from app.services.drafts import get_draft, list_drafts, update_draft, upsert_draft
from app.services.jobs import make_generate_worker, make_send_worker
from app.services.runner import RunState


class FakeState(RunState):
    def __init__(self):
        super().__init__(run_id=1)
        self.events = []

    def emit(self, event):
        self.events.append(event)


class FakeOpenAI:
    def __init__(self, replies):
        self.replies = list(replies)
        outer = self

        class Completions:
            def create(self, **kwargs):
                item = outer.replies.pop(0)
                if isinstance(item, Exception):
                    raise item

                class Msg:
                    content = item

                class Choice:
                    message = Msg()

                class Resp:
                    choices = [Choice()]

                return Resp()

        self.chat = type("Chat", (), {"completions": Completions()})()


class FakeSMTP:
    def __init__(self, fail_on=()):
        self.sent = []
        self.fail_on = set(fail_on)
        self.quit_called = False

    def sendmail(self, from_addr, to_addr, message):
        if to_addr in self.fail_on:
            raise RuntimeError("mailbox full")
        self.sent.append(to_addr)

    def quit(self):
        self.quit_called = True


@pytest.fixture
def contacts(conn):
    seed_templates(conn)
    ids = []
    for name, company, email in [
        ("Ada L", "Acme", "ada@acme.com"),
        ("Bo T", "Bolt", "bo@bolt.com"),
    ]:
        conn.execute(
            """INSERT INTO contacts (company_name, batch, founder_name, predicted_email,
                                     company_description, created_at)
               VALUES (?, 'Winter 2026', ?, ?, 'a startup', ?)""",
            (company, name, email, now_iso()),
        )
        conn.commit()
        ids.append(conn.execute(
            "SELECT id FROM contacts WHERE predicted_email = ?", (email,)
        ).fetchone()["id"])
    return ids


def test_generate_creates_a_draft_per_contact(conn, contacts):
    state = FakeState()
    client = FakeOpenAI(["Body one", "Body two"])
    make_generate_worker(contacts, "job", 0, client=client)(state, conn)
    drafts = list_drafts(conn)
    assert len(drafts) == 2
    assert {d["body"] for d in drafts} == {"Body one", "Body two"}
    assert all(d["status"] == "pending" for d in drafts)
    assert all("Acme" in d["subject"] or "Bolt" in d["subject"] for d in drafts)


def test_generate_records_failures_and_continues(conn, contacts):
    state = FakeState()
    client = FakeOpenAI([RuntimeError("rate limited"), "Body two"])
    make_generate_worker(contacts, "job", 0, client=client)(state, conn)
    drafts = list_drafts(conn)
    assert len(drafts) == 2
    failed = [d for d in drafts if d["status"] == "failed"]
    assert len(failed) == 1
    assert "rate limited" in failed[0]["error"]


def test_generate_followups_do_not_call_openai(conn, contacts):
    state = FakeState()
    client = FakeOpenAI([])  # any call would IndexError
    make_generate_worker(contacts, "job", 1, client=client)(state, conn)
    drafts = list_drafts(conn)
    assert len(drafts) == 2
    assert all("Acme" in d["body"] or "Bolt" in d["body"] for d in drafts)


def test_send_only_sends_approved_drafts(conn, contacts):
    approved = upsert_draft(conn, contacts[0], "job", 0, "S1", "B1")
    update_draft(conn, approved, status="approved")
    pending = upsert_draft(conn, contacts[1], "job", 0, "S2", "B2")

    smtp = FakeSMTP()
    state = FakeState()
    make_send_worker([approved, pending], test_mode=False, delay=0,
                     test_addr="", connect=lambda: ("me@gmail.com", smtp))(state, conn)

    assert smtp.sent == ["ada@acme.com"]
    assert get_draft(conn, approved)["status"] == "sent"
    assert get_draft(conn, pending)["status"] == "pending"
    assert any(e.get("type") == "skipped" for e in state.events)


def test_send_writes_a_sends_row(conn, contacts):
    draft_id = upsert_draft(conn, contacts[0], "job", 0, "S", "B")
    update_draft(conn, draft_id, status="approved")
    smtp = FakeSMTP()
    make_send_worker([draft_id], test_mode=False, delay=0, test_addr="",
                     connect=lambda: ("me@gmail.com", smtp))(FakeState(), conn)
    row = conn.execute("SELECT * FROM sends").fetchone()
    assert row["real_addr"] == "ada@acme.com"
    assert row["to_addr"] == "ada@acme.com"
    assert row["test_mode"] == 0
    assert row["error"] is None
    assert row["draft_id"] == draft_id


def test_test_mode_routes_and_flags(conn, contacts):
    draft_id = upsert_draft(conn, contacts[0], "job", 0, "S", "B")
    update_draft(conn, draft_id, status="approved")
    smtp = FakeSMTP()
    make_send_worker([draft_id], test_mode=True, delay=0, test_addr="me@test.com",
                     connect=lambda: ("me@gmail.com", smtp))(FakeState(), conn)
    row = conn.execute("SELECT * FROM sends").fetchone()
    assert smtp.sent == ["me@test.com"]
    assert row["to_addr"] == "me@test.com"
    assert row["real_addr"] == "ada@acme.com"
    assert row["test_mode"] == 1


def test_send_failure_records_and_continues(conn, contacts):
    first = upsert_draft(conn, contacts[0], "job", 0, "S1", "B1")
    second = upsert_draft(conn, contacts[1], "job", 0, "S2", "B2")
    update_draft(conn, first, status="approved")
    update_draft(conn, second, status="approved")

    smtp = FakeSMTP(fail_on=["ada@acme.com"])
    make_send_worker([first, second], test_mode=False, delay=0, test_addr="",
                     connect=lambda: ("me@gmail.com", smtp))(FakeState(), conn)

    assert smtp.sent == ["bo@bolt.com"]
    assert get_draft(conn, first)["status"] == "failed"
    assert get_draft(conn, second)["status"] == "sent"
    rows = conn.execute("SELECT error FROM sends ORDER BY id").fetchall()
    assert "mailbox full" in rows[0]["error"]
    assert rows[1]["error"] is None


def test_smtp_connect_failure_aborts(conn, contacts):
    draft_id = upsert_draft(conn, contacts[0], "job", 0, "S", "B")
    update_draft(conn, draft_id, status="approved")

    def boom():
        raise RuntimeError("auth failed")

    with pytest.raises(RuntimeError):
        make_send_worker([draft_id], test_mode=False, delay=0, test_addr="",
                         connect=boom)(FakeState(), conn)
    assert conn.execute("SELECT COUNT(*) c FROM sends").fetchone()["c"] == 0


def test_send_stops_when_requested(conn, contacts):
    first = upsert_draft(conn, contacts[0], "job", 0, "S1", "B1")
    second = upsert_draft(conn, contacts[1], "job", 0, "S2", "B2")
    update_draft(conn, first, status="approved")
    update_draft(conn, second, status="approved")

    smtp = FakeSMTP()
    state = FakeState()
    state.stop_requested = True
    make_send_worker([first, second], test_mode=False, delay=0, test_addr="",
                     connect=lambda: ("me@gmail.com", smtp))(state, conn)
    assert smtp.sent == []
