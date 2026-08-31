import json

import pytest

from app.db import now_iso
from app.seed import migrate_sent_log, seed_all


def write_log(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def add_contact(conn, email, company="Acme"):
    conn.execute(
        "INSERT INTO contacts (company_name, founder_name, predicted_email, created_at) "
        "VALUES (?, 'Ada', ?, ?)",
        (company, email, now_iso()),
    )
    conn.commit()


def test_migrates_initial_and_followups(conn, tmp_path):
    add_contact(conn, "ada@acme.com")
    path = write_log(tmp_path / "log.json", {
        "ada@acme.com": {
            "sent_at": "2026-06-26T13:06:49",
            "followups": ["2026-06-30T09:00:00", "2026-07-05T09:00:00"],
        }
    })
    assert migrate_sent_log(conn, path) == 3
    rows = conn.execute("SELECT * FROM sends ORDER BY round").fetchall()
    assert [r["round"] for r in rows] == [0, 1, 2]
    assert rows[0]["sent_at"] == "2026-06-26T13:06:49"
    assert rows[0]["real_addr"] == "ada@acme.com"
    assert rows[0]["to_addr"] == "ada@acme.com"
    assert rows[0]["test_mode"] == 0
    assert rows[0]["error"] is None
    assert rows[0]["contact_id"] is not None


def test_unknown_address_migrates_with_null_contact(conn, tmp_path):
    path = write_log(tmp_path / "log.json", {
        "ghost@nowhere.com": {"sent_at": "2026-06-26T13:06:49", "followups": []}
    })
    assert migrate_sent_log(conn, path) == 1
    row = conn.execute("SELECT * FROM sends").fetchone()
    assert row["contact_id"] is None
    assert row["real_addr"] == "ghost@nowhere.com"


def test_migration_is_idempotent(conn, tmp_path):
    add_contact(conn, "ada@acme.com")
    path = write_log(tmp_path / "log.json", {
        "ada@acme.com": {"sent_at": "2026-06-26T13:06:49", "followups": ["2026-06-30T09:00:00"]}
    })
    migrate_sent_log(conn, path)
    assert migrate_sent_log(conn, path) == 0
    assert conn.execute("SELECT COUNT(*) c FROM sends").fetchone()["c"] == 2


def test_legacy_list_format(conn, tmp_path):
    path = write_log(tmp_path / "log.json", ["ada@acme.com", "bo@bolt.com"])
    assert migrate_sent_log(conn, path) == 2
    assert conn.execute("SELECT COUNT(*) c FROM sends WHERE round=0").fetchone()["c"] == 2


def test_missing_log_returns_zero(conn, tmp_path):
    assert migrate_sent_log(conn, tmp_path / "nope.json") == 0


def test_seed_all_tolerates_missing_csv(conn, tmp_path):
    result = seed_all(conn, csv_path=tmp_path / "nope.csv", log_path=tmp_path / "nope.json")
    assert result["contacts"] == {"inserted": 0, "updated": 0}
    assert result["templates"] == 24
    assert result["sends"] == 0


def test_seed_all_twice_does_not_duplicate(conn, tmp_path):
    import csv as _csv
    csv_path = tmp_path / "c.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["company_name", "founder_name", "predicted_email"])
        w.writerow(["Acme", "Ada", "ada@acme.com"])
    log_path = write_log(tmp_path / "log.json", {
        "ada@acme.com": {"sent_at": "2026-06-26T13:06:49", "followups": []}
    })
    seed_all(conn, csv_path=csv_path, log_path=log_path)
    seed_all(conn, csv_path=csv_path, log_path=log_path)
    assert conn.execute("SELECT COUNT(*) c FROM contacts").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM sends").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM templates").fetchone()["c"] == 24
