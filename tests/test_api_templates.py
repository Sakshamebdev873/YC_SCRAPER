import pytest

from app.db import now_iso
from app.seed import seed_templates


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


@pytest.fixture
def fake_openai(monkeypatch):
    class Completions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)

            class Msg:
                content = "GENERATED BODY"

            class Choice:
                message = Msg()

            class Resp:
                choices = [Choice()]

            return Resp()

    completions = Completions()
    client = type("C", (), {"chat": type("Chat", (), {"completions": completions})()})()
    import app.api.templates as mod
    monkeypatch.setattr(mod, "preview_client_factory", lambda: client)
    return completions


def test_list_domains(client):
    assert client.get("/api/templates/domains").json() == [
        "job", "sales", "sales_professionals"
    ]


def test_get_domain_templates(seeded, client):
    body = client.get("/api/templates/job").json()
    assert body["domain"] == "job"
    assert "system_prompt" in body["templates"]
    assert len(body["keys"]) == 8


def test_get_unknown_domain_404(client):
    assert client.get("/api/templates/nope").status_code == 404


def test_put_saves_and_versions(seeded, client):
    original = client.get("/api/templates/job").json()["templates"]["subject"]
    response = client.put("/api/templates/job/subject", json={"content": "New {company_name}"})
    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert client.get("/api/templates/job").json()["templates"]["subject"] == "New {company_name}"
    versions = client.get("/api/templates/job/subject/versions").json()
    assert versions[0]["content"] == original


def test_put_unknown_key_400(seeded, client):
    assert client.put("/api/templates/job/nope", json={"content": "x"}).status_code == 400


def test_restore_version(seeded, client):
    original = client.get("/api/templates/job").json()["templates"]["subject"]
    client.put("/api/templates/job/subject", json={"content": "v2"})
    version_id = client.get("/api/templates/job/subject/versions").json()[0]["id"]
    response = client.post(f"/api/templates/job/subject/restore/{version_id}")
    assert response.status_code == 200
    assert response.json()["content"] == original


def test_restore_unknown_version_404(seeded, client):
    assert client.post("/api/templates/job/subject/restore/999").status_code == 404


def test_preview_uses_unsaved_content(seeded, client, fake_openai):
    response = client.post("/api/templates/preview", json={
        "domain": "job", "key": "system_prompt",
        "content": "UNSAVED SYSTEM PROMPT", "round": 0,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["body"] == "GENERATED BODY"
    assert body["contact"]["company_name"] == "Acme"
    sent_system = fake_openai.calls[0]["messages"][0]["content"]
    assert sent_system == "UNSAVED SYSTEM PROMPT"
    # nothing was written
    assert client.get("/api/templates/job").json()["templates"]["system_prompt"] != \
        "UNSAVED SYSTEM PROMPT"


def test_preview_followup_does_not_call_openai(seeded, client, fake_openai):
    body = client.post("/api/templates/preview", json={
        "domain": "job", "key": "followup_2",
        "content": "Nudge about {company_name}.", "round": 2,
    }).json()
    assert body["body"] == "Nudge about Acme."
    assert fake_openai.calls == []


def test_preview_without_contacts_400(conn, client, fake_openai):
    seed_templates(conn)
    assert client.post("/api/templates/preview", json={
        "domain": "job", "key": "subject", "content": "x", "round": 0,
    }).status_code == 400
