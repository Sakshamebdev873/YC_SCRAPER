from datetime import datetime, timedelta

import pytest

from app.db import now_iso
from app.seed import seed_templates
from app.services.drafts import upsert_draft


@pytest.fixture
def seeded(conn):
    seed_templates(conn)
    for name, company, email in [("Ada L", "Acme", "ada@acme.com"),
                                 ("Bo T", "Bolt", "bo@bolt.com")]:
        conn.execute(
            """INSERT INTO contacts (company_name, batch, founder_name, predicted_email,
                                     company_description, created_at)
               VALUES (?, 'Winter 2026', ?, ?, 'a startup', ?)""",
            (company, name, email, now_iso()),
        )
    conn.commit()
    return conn


@pytest.fixture
def fake_openai(monkeypatch):
    class Completions:
        def create(self, **kwargs):
            class Msg:
                content = "REGENERATED"

            class Choice:
                message = Msg()

            class Resp:
                choices = [Choice()]

            return Resp()

    client = type("C", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    import app.api.drafts as mod
    monkeypatch.setattr(mod, "regenerate_client_factory", lambda: client)
    return client


def contact_ids(conn):
    return [r["id"] for r in conn.execute("SELECT id FROM contacts ORDER BY id")]


def test_queue_initial(seeded, client):
    body = client.get("/api/queue?domain=job&round=0").json()
    assert body["total"] == 2
    assert {i["company_name"] for i in body["items"]} == {"Acme", "Bolt"}


def test_queue_respects_limit_and_batch(seeded, client):
    assert client.get("/api/queue?limit=1").json()["total"] == 1
    assert client.get("/api/queue?batch=W26").json()["total"] == 2
    assert client.get("/api/queue?batch=Spring 2026").json()["total"] == 0


def test_queue_followup_round(seeded, client):
    old = (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds")
    conn = seeded
    conn.execute(
        """INSERT INTO sends (contact_id, round, to_addr, real_addr, sent_at, test_mode)
           VALUES (?, 0, 'ada@acme.com', 'ada@acme.com', ?, 0)""",
        (contact_ids(conn)[0], old),
    )
    conn.commit()
    body = client.get("/api/queue?round=1").json()
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "Acme"


def test_queue_leads_for_sales(conn, client):
    seed_templates(conn)
    assert client.post("/api/queue/leads", json={"domain": "sales", "count": 3}).json() == \
        {"created": 3}
    assert client.get("/api/queue?domain=sales").json()["total"] == 3


def test_queue_leads_rejects_job_domain(conn, client):
    assert client.post("/api/queue/leads",
                       json={"domain": "job", "count": 1}).status_code == 400


def test_list_and_filter_drafts(seeded, client):
    ids = contact_ids(seeded)
    upsert_draft(seeded, ids[0], "job", 0, "S1", "B1")
    approved = upsert_draft(seeded, ids[1], "job", 0, "S2", "B2")
    client.patch(f"/api/drafts/{approved}", json={"status": "approved"})
    assert len(client.get("/api/drafts").json()) == 2
    assert len(client.get("/api/drafts?status=approved").json()) == 1


def test_patch_draft_edits_body(seeded, client):
    draft_id = upsert_draft(seeded, contact_ids(seeded)[0], "job", 0, "S", "B")
    body = client.patch(f"/api/drafts/{draft_id}", json={"body": "Edited"}).json()
    assert body["body"] == "Edited"
    assert body["edited_at"] is not None


def test_patch_draft_bad_status_and_missing(seeded, client):
    draft_id = upsert_draft(seeded, contact_ids(seeded)[0], "job", 0, "S", "B")
    assert client.patch(f"/api/drafts/{draft_id}",
                        json={"status": "nope"}).status_code == 400
    assert client.patch("/api/drafts/999", json={"status": "approved"}).status_code == 404


def test_bulk_status(seeded, client):
    ids = contact_ids(seeded)
    a = upsert_draft(seeded, ids[0], "job", 0, "S1", "B1")
    b = upsert_draft(seeded, ids[1], "job", 0, "S2", "B2")
    assert client.post("/api/drafts/bulk-status",
                       json={"draft_ids": [a, b], "status": "approved"}).json() == \
        {"updated": 2}
    assert len(client.get("/api/drafts?status=approved").json()) == 2


def test_regenerate(seeded, client, fake_openai):
    draft_id = upsert_draft(seeded, contact_ids(seeded)[0], "job", 0, "S", "OLD")
    body = client.post(f"/api/drafts/{draft_id}/regenerate").json()
    assert body["body"] == "REGENERATED"
    assert body["status"] == "pending"


def test_regenerate_unknown_404(client, fake_openai):
    assert client.post("/api/drafts/999/regenerate").status_code == 404


def test_followups_due(seeded, client):
    conn = seeded
    old = (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO sends (contact_id, round, to_addr, real_addr, sent_at, test_mode)
           VALUES (?, 0, 'ada@acme.com', 'ada@acme.com', ?, 0)""",
        (contact_ids(conn)[0], old),
    )
    conn.commit()
    body = client.get("/api/followups/due").json()
    assert body["1"]["count"] == 1
    assert body["2"]["count"] == 0
    assert body["1"]["items"][0]["company_name"] == "Acme"
