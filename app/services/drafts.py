"""Draft CRUD.

A draft is one generated-and-reviewable email for a (contact, round).
Only one live draft exists per pair; 'sent' and 'rejected' rows are kept
as history.
"""

from app.db import now_iso

DRAFT_STATUSES = ["pending", "approved", "rejected", "sent", "failed"]
_LIVE = ("pending", "approved", "failed")

_SELECT = """
SELECT d.*, c.founder_name, c.company_name, c.predicted_email, c.batch
FROM drafts d JOIN contacts c ON c.id = d.contact_id
"""

_UNSET = object()


def upsert_draft(conn, contact_id, domain, round_num, subject, body,
                 status: str = "pending", error=None) -> int:
    if status not in DRAFT_STATUSES:
        raise ValueError(f"Unknown draft status '{status}'")
    conn.execute(
        f"""DELETE FROM drafts WHERE contact_id = ? AND round = ?
            AND status IN ({', '.join('?' * len(_LIVE))})""",
        (contact_id, round_num, *_LIVE),
    )
    cur = conn.execute(
        """INSERT INTO drafts (contact_id, domain, round, subject, body,
                               status, generated_at, edited_at, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
        (contact_id, domain, round_num, subject, body, status, now_iso(), error),
    )
    conn.commit()
    return cur.lastrowid


def get_draft(conn, draft_id):
    row = conn.execute(_SELECT + " WHERE d.id = ?", (draft_id,)).fetchone()
    return dict(row) if row else None


def list_drafts(conn, status=None, round_num=None, domain=None, limit: int = 0) -> list:
    sql = _SELECT
    clauses, params = [], []
    if status:
        clauses.append("d.status = ?")
        params.append(status)
    if round_num is not None:
        clauses.append("d.round = ?")
        params.append(round_num)
    if domain:
        clauses.append("d.domain = ?")
        params.append(domain)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY d.id DESC"
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def update_draft(conn, draft_id, *, subject=None, body=None, status=None,
                 error=_UNSET) -> dict:
    existing = get_draft(conn, draft_id)
    if not existing:
        raise ValueError(f"Unknown draft {draft_id}")
    if status is not None and status not in DRAFT_STATUSES:
        raise ValueError(f"Unknown draft status '{status}'")

    fields, params = [], []
    if subject is not None:
        fields.append("subject = ?")
        params.append(subject)
    if body is not None:
        fields.append("body = ?")
        params.append(body)
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if error is not _UNSET:
        fields.append("error = ?")
        params.append(error)
    if subject is not None or body is not None:
        fields.append("edited_at = ?")
        params.append(now_iso())
    if fields:
        conn.execute(
            f"UPDATE drafts SET {', '.join(fields)} WHERE id = ?", (*params, draft_id)
        )
        conn.commit()
    return get_draft(conn, draft_id)
