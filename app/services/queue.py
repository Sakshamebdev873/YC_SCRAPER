"""Who is eligible to be emailed, and when.

Lifted from send_emails.py so the CLI and the web UI apply exactly the
same rules against exactly the same data.
"""

from datetime import datetime, timedelta

from yc_scraper.spiders.yc_spider import BATCH_NAME_MAP

# Minimum days before each follow-up round; index = round number.
FOLLOWUP_MIN_DAYS = [0, 3, 4, 5]

_REAL_SEND = "test_mode = 0 AND error IS NULL"


def resolve_batch(value: str) -> str:
    """Accepts either a short code (W26) or the stored full name (Winter 2026)."""
    if not value:
        return ""
    return BATCH_NAME_MAP.get(value.upper(), value)


def dedupe_by_company(rows: list) -> list:
    """One contact per company, preferring a CEO.

    Never email multiple people at the same company — they compare notes
    and it reads as a mass blast.
    """
    best = {}
    for row in rows:
        company = row["company_name"]
        existing = best.get(company)
        if existing is None:
            best[company] = row
        elif ("ceo" in (row.get("founder_title") or "").lower()
              and "ceo" not in (existing.get("founder_title") or "").lower()):
            best[company] = row
    return list(best.values())


def contacted_emails(conn) -> set:
    rows = conn.execute(f"SELECT DISTINCT real_addr FROM sends WHERE {_REAL_SEND}")
    return {r["real_addr"] for r in rows}


def contacted_companies(conn) -> set:
    rows = conn.execute(
        f"""SELECT DISTINCT c.company_name FROM sends s
            JOIN contacts c ON c.predicted_email = s.real_addr
            WHERE {_REAL_SEND}"""
    )
    return {r["company_name"] for r in rows}


def eligible_initial(conn, domain: str = "job", batch: str = "", limit: int = 0) -> list:
    sql = """SELECT * FROM contacts
             WHERE domain = ? AND status = 'active'
               AND predicted_email != ''
               AND founder_name NOT IN ('Unknown', '')"""
    params = [domain]
    resolved = resolve_batch(batch)
    if resolved:
        sql += " AND batch = ?"
        params.append(resolved)
    sql += " ORDER BY id"

    rows = [dict(r) for r in conn.execute(sql, params)]
    emails = contacted_emails(conn)
    companies = contacted_companies(conn)
    rows = [
        r for r in rows
        if r["predicted_email"] not in emails and r["company_name"] not in companies
    ]
    rows = dedupe_by_company(rows)
    return rows[:limit] if limit > 0 else rows


def send_history(conn, real_addr: str) -> dict:
    rows = conn.execute(
        f"""SELECT round, sent_at FROM sends
            WHERE real_addr = ? AND {_REAL_SEND} ORDER BY round, id""",
        (real_addr,),
    ).fetchall()
    sent_at = next((r["sent_at"] for r in rows if r["round"] == 0), None)
    followups = [r["sent_at"] for r in rows if r["round"] > 0]
    return {"sent_at": sent_at, "followups": followups}


def followup_eligible(entry: dict, round_num: int) -> bool:
    """True once enough days have passed since the previous contact."""
    min_days = FOLLOWUP_MIN_DAYS[round_num]
    if round_num == 1:
        last_contact = entry.get("sent_at")
    else:
        followups = entry.get("followups") or []
        if len(followups) < round_num - 1:
            return False
        last_contact = followups[round_num - 2]
    if not last_contact:
        return False
    return datetime.now() - datetime.fromisoformat(last_contact) >= timedelta(days=min_days)


def eligible_followup(conn, domain: str = "job", round_num: int = 1, limit: int = 0) -> list:
    rows = [dict(r) for r in conn.execute(
        """SELECT * FROM contacts
           WHERE domain = ? AND status = 'active' AND predicted_email != ''
             AND founder_name NOT IN ('Unknown', '')
           ORDER BY id""",
        (domain,),
    )]
    out = []
    for row in rows:
        history = send_history(conn, row["predicted_email"])
        if not history["sent_at"]:
            continue
        if len(history["followups"]) >= round_num:
            continue
        if not followup_eligible(history, round_num):
            continue
        row["history"] = history
        out.append(row)
    return out[:limit] if limit > 0 else out


def followup_due_counts(conn, domain: str = "job") -> dict:
    return {n: len(eligible_followup(conn, domain, n)) for n in (1, 2, 3)}
