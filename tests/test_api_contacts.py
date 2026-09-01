from app.db import now_iso
from app.seed import seed_templates


def add(conn, email, company, batch="Winter 2026", status="active", name="Ada L"):
    conn.execute(
        """INSERT INTO contacts (company_name, batch, founder_name, predicted_email,
                                 status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (company, batch, name, email, status, now_iso()),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM contacts WHERE predicted_email = ?", (email,)
    ).fetchone()["id"]


def test_stats(conn, client):
    seed_templates(conn)
    add(conn, "ada@acme.com", "Acme")
    response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["contacts"] == 1
    assert body["contacted"] == 0
    assert body["followups_due"] == {"1": 0, "2": 0, "3": 0}


def test_list_contacts_paginates(conn, client):
    for i in range(5):
        add(conn, f"a{i}@acme.com", f"Co{i}")
    body = client.get("/api/contacts?per_page=2&page=2").json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 2


def test_search_matches_company_founder_and_email(conn, client):
    add(conn, "ada@acme.com", "Acme", name="Ada Lovelace")
    add(conn, "bo@bolt.com", "Bolt", name="Bo Tanical")
    assert len(client.get("/api/contacts?search=acme").json()["items"]) == 1
    assert len(client.get("/api/contacts?search=Lovelace").json()["items"]) == 1
    assert len(client.get("/api/contacts?search=bolt.com").json()["items"]) == 1
    assert len(client.get("/api/contacts?search=zzz").json()["items"]) == 0


def test_filter_by_batch_and_status(conn, client):
    add(conn, "ada@acme.com", "Acme", batch="Winter 2026")
    add(conn, "bo@bolt.com", "Bolt", batch="Spring 2026", status="skipped")
    assert len(client.get("/api/contacts?batch=Spring 2026").json()["items"]) == 1
    assert len(client.get("/api/contacts?status=skipped").json()["items"]) == 1


def test_contacted_flag(conn, client):
    add(conn, "ada@acme.com", "Acme")
    conn.execute(
        """INSERT INTO sends (contact_id, round, to_addr, real_addr, sent_at, test_mode)
           VALUES (1, 0, 'ada@acme.com', 'ada@acme.com', ?, 0)""",
        (now_iso(),),
    )
    conn.commit()
    assert client.get("/api/contacts").json()["items"][0]["contacted"] is True


def test_batches_endpoint(conn, client):
    add(conn, "ada@acme.com", "Acme", batch="Winter 2026")
    add(conn, "bo@bolt.com", "Bolt", batch="Spring 2026")
    assert client.get("/api/contacts/batches").json() == ["Spring 2026", "Winter 2026"]


def test_patch_email_and_status(conn, client):
    contact_id = add(conn, "ada@acme.com", "Acme")
    response = client.patch(f"/api/contacts/{contact_id}",
                            json={"predicted_email": "ada.l@acme.com"})
    assert response.status_code == 200
    assert response.json()["predicted_email"] == "ada.l@acme.com"
    assert client.patch(f"/api/contacts/{contact_id}",
                        json={"status": "skipped"}).json()["status"] == "skipped"


def test_patch_rejects_bad_status(conn, client):
    contact_id = add(conn, "ada@acme.com", "Acme")
    assert client.patch(f"/api/contacts/{contact_id}",
                        json={"status": "nope"}).status_code == 400


def test_patch_unknown_id(client):
    assert client.patch("/api/contacts/999", json={"status": "skipped"}).status_code == 404


def test_patch_duplicate_email_conflicts(conn, client):
    add(conn, "ada@acme.com", "Acme")
    other = add(conn, "bo@bolt.com", "Bolt")
    assert client.patch(f"/api/contacts/{other}",
                        json={"predicted_email": "ada@acme.com"}).status_code == 409


def test_import_endpoint(conn, client, tmp_path):
    import csv as _csv
    path = tmp_path / "c.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerow(["company_name", "founder_name", "predicted_email"])
        writer.writerow(["Acme", "Ada", "ada@acme.com"])
    response = client.post("/api/contacts/import", json={"csv_path": str(path)})
    assert response.json() == {"inserted": 1, "updated": 0}
    assert client.get("/api/contacts").json()["total"] == 1


def test_import_missing_file_404(client, tmp_path):
    assert client.post("/api/contacts/import",
                       json={"csv_path": str(tmp_path / "nope.csv")}).status_code == 404
