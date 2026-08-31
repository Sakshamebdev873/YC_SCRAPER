"""Template storage: read, save with version snapshot, restore.

Templates seed from domains/*.py on first run (see app/seed.py) and are
editable from there on. Every save archives the previous content so a
prompt that worked better can be brought back.
"""

from app.db import now_iso

DOMAIN_KEYS = ["job", "sales", "sales_professionals"]

TEMPLATE_KEYS = [
    "bio", "system_prompt", "user_prompt", "subject",
    "followup_subject", "followup_1", "followup_2", "followup_3",
]


def _check(domain: str, key: str | None = None) -> None:
    if domain not in DOMAIN_KEYS:
        raise ValueError(f"Unknown domain '{domain}'. Choices: {', '.join(DOMAIN_KEYS)}")
    if key is not None and key not in TEMPLATE_KEYS:
        raise ValueError(f"Unknown template key '{key}'. Choices: {', '.join(TEMPLATE_KEYS)}")


def get_templates(conn, domain: str) -> dict:
    _check(domain)
    rows = conn.execute(
        "SELECT key, content FROM templates WHERE domain = ?", (domain,)
    ).fetchall()
    return {r["key"]: r["content"] for r in rows}


def get_template(conn, domain: str, key: str):
    _check(domain, key)
    row = conn.execute(
        "SELECT content FROM templates WHERE domain = ? AND key = ?", (domain, key)
    ).fetchone()
    return row["content"] if row else None


def save_template(conn, domain: str, key: str, content: str) -> int:
    """Archives the current content, then writes the new content."""
    _check(domain, key)
    version_id = 0
    previous = get_template(conn, domain, key)
    if previous is not None and previous != content:
        cur = conn.execute(
            "INSERT INTO template_versions (domain, key, content, created_at) VALUES (?, ?, ?, ?)",
            (domain, key, previous, now_iso()),
        )
        version_id = cur.lastrowid
    conn.execute(
        """INSERT INTO templates (domain, key, content, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(domain, key) DO UPDATE SET content = excluded.content,
                                                  updated_at = excluded.updated_at""",
        (domain, key, content, now_iso()),
    )
    conn.commit()
    return version_id


def list_versions(conn, domain: str, key: str, limit: int = 20) -> list:
    _check(domain, key)
    rows = conn.execute(
        """SELECT id, content, created_at FROM template_versions
           WHERE domain = ? AND key = ? ORDER BY id DESC LIMIT ?""",
        (domain, key, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def restore_version(conn, version_id: int) -> dict:
    row = conn.execute(
        "SELECT domain, key, content FROM template_versions WHERE id = ?", (version_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown template version {version_id}")
    save_template(conn, row["domain"], row["key"], row["content"])
    return {"domain": row["domain"], "key": row["key"], "content": row["content"]}
