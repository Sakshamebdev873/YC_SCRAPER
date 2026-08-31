"""SQLite schema and connection handling.

This is the only module that owns DDL. Everything else goes through
get_conn() and speaks DML only.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path("output") / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name        TEXT NOT NULL DEFAULT '',
    batch               TEXT NOT NULL DEFAULT '',
    company_website     TEXT NOT NULL DEFAULT '',
    founder_name        TEXT NOT NULL DEFAULT '',
    founder_title       TEXT NOT NULL DEFAULT '',
    founder_linkedin    TEXT NOT NULL DEFAULT '',
    founder_twitter     TEXT NOT NULL DEFAULT '',
    predicted_email     TEXT NOT NULL UNIQUE,
    email_pattern       TEXT NOT NULL DEFAULT '',
    yc_url              TEXT NOT NULL DEFAULT '',
    company_description TEXT NOT NULL DEFAULT '',
    domain              TEXT NOT NULL DEFAULT 'job',
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contacts_batch   ON contacts(batch);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_name);
CREATE INDEX IF NOT EXISTS idx_contacts_status  ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_contacts_domain  ON contacts(domain);

CREATE TABLE IF NOT EXISTS templates (
    domain     TEXT NOT NULL,
    key        TEXT NOT NULL,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (domain, key)
);

CREATE TABLE IF NOT EXISTS template_versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    domain     TEXT NOT NULL,
    key        TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_template_versions
    ON template_versions(domain, key, id DESC);

CREATE TABLE IF NOT EXISTS drafts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id   INTEGER NOT NULL REFERENCES contacts(id),
    domain       TEXT NOT NULL,
    round        INTEGER NOT NULL DEFAULT 0,
    subject      TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    generated_at TEXT NOT NULL,
    edited_at    TEXT,
    error        TEXT
);
-- One live draft per (contact, round). 'sent' and 'rejected' drafts are
-- historical records and deliberately excluded.
CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_live
    ON drafts(contact_id, round)
    WHERE status IN ('pending', 'approved', 'failed');
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status, round);

CREATE TABLE IF NOT EXISTS sends (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    draft_id   INTEGER REFERENCES drafts(id),
    round      INTEGER NOT NULL DEFAULT 0,
    to_addr    TEXT NOT NULL,
    real_addr  TEXT NOT NULL,
    sent_at    TEXT NOT NULL,
    test_mode  INTEGER NOT NULL DEFAULT 0,
    error      TEXT
);
CREATE INDEX IF NOT EXISTS idx_sends_real    ON sends(real_addr);
CREATE INDEX IF NOT EXISTS idx_sends_contact ON sends(contact_id, round);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    domain      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',
    total       INTEGER NOT NULL DEFAULT 0,
    completed   INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_conn(db_path=None) -> sqlite3.Connection:
    """Opens a connection with row dicts, WAL, and FK enforcement.

    check_same_thread=False because FastAPI serves sync endpoints from a
    threadpool. Background workers still open their own connection.
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
