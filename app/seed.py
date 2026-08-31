"""Idempotent import of existing on-disk state into the SQLite DB.

Safe to run on every boot. Nothing here ever writes to the CSV or to
sent_log.json — those stay on disk as read-only inputs and backups.
"""

import csv
from pathlib import Path

from app.db import now_iso

CSV_FIELDS = [
    "company_name", "batch", "company_website", "founder_name", "founder_title",
    "founder_linkedin", "founder_twitter", "predicted_email", "email_pattern",
    "yc_url", "company_description",
]


def import_contacts(conn, csv_path, domain: str = "job") -> dict:
    """Upserts CSV rows into contacts, keyed on predicted_email."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    inserted = updated = 0
    for row in rows:
        email = (row.get("predicted_email") or "").strip()
        if not email:
            continue
        values = {k: (row.get(k) or "").strip() for k in CSV_FIELDS}
        values["predicted_email"] = email
        existing = conn.execute(
            "SELECT id FROM contacts WHERE predicted_email = ?", (email,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE contacts SET company_name=:company_name, batch=:batch,
                       company_website=:company_website, founder_name=:founder_name,
                       founder_title=:founder_title, founder_linkedin=:founder_linkedin,
                       founder_twitter=:founder_twitter, email_pattern=:email_pattern,
                       yc_url=:yc_url, company_description=:company_description
                   WHERE predicted_email=:predicted_email""",
                values,
            )
            updated += 1
        else:
            conn.execute(
                f"""INSERT INTO contacts ({', '.join(CSV_FIELDS)}, domain, status, created_at)
                    VALUES ({', '.join(':' + k for k in CSV_FIELDS)}, :domain, 'active', :created_at)""",
                {**values, "domain": domain, "created_at": now_iso()},
            )
            inserted += 1
    conn.commit()
    return {"inserted": inserted, "updated": updated}
