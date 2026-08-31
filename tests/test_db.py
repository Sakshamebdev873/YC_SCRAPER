from app.db import init_db, now_iso

EXPECTED_TABLES = {
    "contacts", "templates", "template_versions",
    "drafts", "sends", "runs", "settings",
}


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {r["name"] for r in rows}


def test_init_db_creates_all_tables(conn):
    assert EXPECTED_TABLES <= table_names(conn)


def test_init_db_is_idempotent(conn):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('send_delay', '30')"
    )
    conn.commit()
    init_db(conn)
    rows = conn.execute("SELECT value FROM settings WHERE key='send_delay'").fetchall()
    assert [r["value"] for r in rows] == ["30"]


def test_rows_are_mappings(conn):
    conn.execute("INSERT INTO settings (key, value) VALUES ('a', 'b')")
    conn.commit()
    row = conn.execute("SELECT * FROM settings").fetchone()
    assert row["key"] == "a"


def test_predicted_email_is_unique(conn):
    import sqlite3
    stmt = (
        "INSERT INTO contacts (company_name, predicted_email, created_at) "
        "VALUES (?, ?, ?)"
    )
    conn.execute(stmt, ("Acme", "a@acme.com", now_iso()))
    conn.commit()
    try:
        conn.execute(stmt, ("Acme2", "a@acme.com", now_iso()))
        conn.commit()
        raise AssertionError("expected IntegrityError")
    except sqlite3.IntegrityError:
        pass


def test_active_draft_uniqueness_per_contact_and_round(conn):
    import sqlite3
    conn.execute(
        "INSERT INTO contacts (company_name, predicted_email, created_at) VALUES (?, ?, ?)",
        ("Acme", "a@acme.com", now_iso()),
    )
    conn.commit()
    cid = conn.execute("SELECT id FROM contacts").fetchone()["id"]
    stmt = (
        "INSERT INTO drafts (contact_id, domain, round, subject, body, status, generated_at) "
        "VALUES (?, 'job', 0, 's', 'b', ?, ?)"
    )
    conn.execute(stmt, (cid, "pending", now_iso()))
    conn.commit()
    try:
        conn.execute(stmt, (cid, "pending", now_iso()))
        conn.commit()
        raise AssertionError("expected IntegrityError")
    except sqlite3.IntegrityError:
        conn.rollback()
    # 'sent' and 'rejected' drafts are historical and excluded from the index
    conn.execute(stmt, (cid, "sent", now_iso()))
    conn.execute(stmt, (cid, "rejected", now_iso()))
    conn.commit()
