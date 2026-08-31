import csv

from app.seed import import_contacts

HEADERS = [
    "company_name", "batch", "company_website", "founder_name", "founder_title",
    "founder_linkedin", "founder_twitter", "predicted_email", "email_pattern",
    "yc_url", "company_description",
]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in HEADERS})
    return path


def test_imports_rows(conn, tmp_path):
    path = write_csv(tmp_path / "c.csv", [
        {"company_name": "Acme", "batch": "Winter 2026", "founder_name": "Ada L",
         "predicted_email": "ada@acme.com", "company_description": "robots"},
        {"company_name": "Bolt", "batch": "Winter 2026", "founder_name": "Bo T",
         "predicted_email": "bo@bolt.com"},
    ])
    result = import_contacts(conn, path)
    assert result == {"inserted": 2, "updated": 0}
    rows = conn.execute("SELECT * FROM contacts ORDER BY company_name").fetchall()
    assert [r["company_name"] for r in rows] == ["Acme", "Bolt"]
    assert rows[0]["domain"] == "job"
    assert rows[0]["status"] == "active"


def test_import_is_idempotent(conn, tmp_path):
    path = write_csv(tmp_path / "c.csv", [
        {"company_name": "Acme", "founder_name": "Ada", "predicted_email": "ada@acme.com"},
    ])
    import_contacts(conn, path)
    result = import_contacts(conn, path)
    assert result == {"inserted": 0, "updated": 1}
    assert conn.execute("SELECT COUNT(*) c FROM contacts").fetchone()["c"] == 1


def test_import_preserves_status(conn, tmp_path):
    path = write_csv(tmp_path / "c.csv", [
        {"company_name": "Acme", "founder_name": "Ada", "predicted_email": "ada@acme.com"},
    ])
    import_contacts(conn, path)
    conn.execute("UPDATE contacts SET status='skipped'")
    conn.commit()
    import_contacts(conn, path)
    assert conn.execute("SELECT status FROM contacts").fetchone()["status"] == "skipped"


def test_skips_rows_without_email(conn, tmp_path):
    path = write_csv(tmp_path / "c.csv", [
        {"company_name": "Acme", "founder_name": "Ada", "predicted_email": ""},
    ])
    assert import_contacts(conn, path) == {"inserted": 0, "updated": 0}
    assert conn.execute("SELECT COUNT(*) c FROM contacts").fetchone()["c"] == 0


def test_missing_csv_raises(conn, tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        import_contacts(conn, tmp_path / "nope.csv")
