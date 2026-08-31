"""The DB-backed queue must select exactly what the old CSV + sent_log
logic selected. The reference implementation below is the pre-refactor
code, kept here on purpose."""

from datetime import datetime, timedelta

from app.db import now_iso
from app.services.queue import eligible_initial


def reference_queue(rows, sent_log):
    contacted_companies = {
        r["company_name"] for r in rows if r.get("predicted_email") in sent_log
    }
    candidates = [
        r for r in rows
        if r.get("predicted_email")
        and r["founder_name"] not in ("Unknown", "")
        and r["predicted_email"] not in sent_log
        and r["company_name"] not in contacted_companies
    ]
    best = {}
    for row in candidates:
        company = row["company_name"]
        existing = best.get(company)
        if existing is None:
            best[company] = row
        elif ("ceo" in row.get("founder_title", "").lower()
              and "ceo" not in existing.get("founder_title", "").lower()):
            best[company] = row
    return sorted(r["predicted_email"] for r in best.values())


ROWS = [
    {"company_name": "Acme", "founder_name": "Ada L", "founder_title": "Founder",
     "predicted_email": "ada@acme.com", "batch": "Winter 2026"},
    {"company_name": "Acme", "founder_name": "Bo T", "founder_title": "CEO",
     "predicted_email": "bo@acme.com", "batch": "Winter 2026"},
    {"company_name": "Bolt", "founder_name": "Cy R", "founder_title": "CTO",
     "predicted_email": "cy@bolt.com", "batch": "Winter 2026"},
    {"company_name": "Cog", "founder_name": "Unknown", "founder_title": "",
     "predicted_email": "x@cog.com", "batch": "Winter 2026"},
    {"company_name": "Dex", "founder_name": "Di X", "founder_title": "Founder",
     "predicted_email": "di@dex.com", "batch": "Winter 2026"},
]

SENT_LOG = {"di@dex.com": {"sent_at": "2026-06-01T10:00:00", "followups": []}}


def load(conn):
    for r in ROWS:
        conn.execute(
            """INSERT INTO contacts (company_name, batch, founder_name, founder_title,
                                     predicted_email, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (r["company_name"], r["batch"], r["founder_name"], r["founder_title"],
             r["predicted_email"], now_iso()),
        )
    for email, entry in SENT_LOG.items():
        contact = conn.execute(
            "SELECT id FROM contacts WHERE predicted_email = ?", (email,)
        ).fetchone()
        conn.execute(
            """INSERT INTO sends (contact_id, draft_id, round, to_addr, real_addr,
                                  sent_at, test_mode, error)
               VALUES (?, NULL, 0, ?, ?, ?, 0, NULL)""",
            (contact["id"], email, email, entry["sent_at"]),
        )
    conn.commit()


def test_db_queue_matches_the_old_logic(conn):
    load(conn)
    got = sorted(r["predicted_email"] for r in eligible_initial(conn))
    assert got == reference_queue(ROWS, SENT_LOG)
    assert got == ["bo@acme.com", "cy@bolt.com"]
