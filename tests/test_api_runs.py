import time

import pytest

from app.db import now_iso
from app.seed import seed_templates
from app.services.drafts import get_draft, upsert_draft, update_draft


@pytest.fixture
def seeded(conn):
    seed_templates(conn)
    conn.execute(
        """INSERT INTO contacts (company_name, batch, founder_name, predicted_email,
                                 company_description, created_at)
           VALUES ('Acme', 'Winter 2026', 'Ada L', 'ada@acme.com', 'robots', ?)""",
        (now_iso(),),
    )
    conn.commit()
    return conn


def contact_id(conn):
    return conn.execute("SELECT id FROM contacts").fetchone()["id"]


def wait_for_status(conn, run_id, wanted, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row and row["status"] == wanted:
            return True
        time.sleep(0.05)
    return False


def test_generate_run_creates_drafts(seeded, client, monkeypatch):
    import app.api.runs as mod
    from app.services.drafts import upsert_draft as real_upsert

    def fake_factory(contact_ids, domain, round_num):
        def worker(state, conn):
            for cid in contact_ids:
                real_upsert(conn, cid, domain, round_num, "S", "B")
        return worker

    monkeypatch.setattr(mod, "generate_worker_factory", fake_factory)
    response = client.post("/api/runs/generate", json={
        "contact_ids": [contact_id(seeded)], "domain": "job", "round": 0,
    })
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert wait_for_status(seeded, run_id, "done")
    assert len(client.get("/api/drafts").json()) == 1


def test_generate_rejects_empty(client):
    assert client.post("/api/runs/generate",
                       json={"contact_ids": [], "domain": "job", "round": 0}).status_code == 400


def test_send_rejects_unapproved_drafts(seeded, client):
    draft_id = upsert_draft(seeded, contact_id(seeded), "job", 0, "S", "B")
    response = client.post("/api/runs/send", json={
        "draft_ids": [draft_id], "test_mode": True, "test_email": "me@test.com",
    })
    assert response.status_code == 400
    assert "approved" in response.json()["detail"]


def test_send_rejects_unknown_draft(client):
    assert client.post("/api/runs/send", json={
        "draft_ids": [999], "test_mode": True, "test_email": "me@test.com",
    }).status_code == 400


def test_send_test_mode_needs_an_address(seeded, client, monkeypatch):
    monkeypatch.setenv("TEST_EMAIL", "")
    draft_id = upsert_draft(seeded, contact_id(seeded), "job", 0, "S", "B")
    update_draft(seeded, draft_id, status="approved")
    response = client.post("/api/runs/send",
                           json={"draft_ids": [draft_id], "test_mode": True})
    assert response.status_code == 400


def test_send_run_marks_draft_sent(seeded, client, monkeypatch):
    import app.api.runs as mod
    draft_id = upsert_draft(seeded, contact_id(seeded), "job", 0, "S", "B")
    update_draft(seeded, draft_id, status="approved")

    def fake_factory(draft_ids, test_mode, delay, test_addr):
        def worker(state, conn):
            from app.services.drafts import update_draft as upd
            for did in draft_ids:
                upd(conn, did, status="sent")
        return worker

    monkeypatch.setattr(mod, "send_worker_factory", fake_factory)
    response = client.post("/api/runs/send", json={
        "draft_ids": [draft_id], "test_mode": True, "test_email": "me@test.com", "delay": 0,
    })
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert wait_for_status(seeded, run_id, "done")
    assert get_draft(seeded, draft_id)["status"] == "sent"


def test_run_detail_and_list(seeded, client, monkeypatch):
    import app.api.runs as mod
    monkeypatch.setattr(mod, "generate_worker_factory",
                        lambda *a, **k: (lambda state, conn: None))
    run_id = client.post("/api/runs/generate", json={
        "contact_ids": [contact_id(seeded)], "domain": "job", "round": 0,
    }).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["id"] == run_id
    assert client.get("/api/runs").json()[0]["id"] == run_id
    assert client.get("/api/runs/9999").status_code == 404


def test_events_stream_closes_for_a_finished_run(seeded, client, monkeypatch):
    import app.api.runs as mod
    monkeypatch.setattr(mod, "generate_worker_factory",
                        lambda *a, **k: (lambda state, conn: None))
    run_id = client.post("/api/runs/generate", json={
        "contact_ids": [contact_id(seeded)], "domain": "job", "round": 0,
    }).json()["run_id"]
    assert wait_for_status(seeded, run_id, "done")
    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())
    assert "snapshot" in payload
    assert "done" in payload


def test_stop_unknown_run(client):
    assert client.post("/api/runs/9999/stop").json() == {"stopped": False}


def test_config_never_leaks_secrets(client, monkeypatch):
    monkeypatch.setenv("GMAIL_EMAIL", "me@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "hunter2hunter2")
    body = client.get("/api/runs/config").json()
    assert body["gmail_configured"] is True
    assert "hunter2hunter2" not in str(body)
