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


def _job_templates() -> dict:
    from domains import job_application as j

    return {
        "bio": j.CANDIDATE_BIO,
        "system_prompt": j.SYSTEM_PROMPT,
        "user_prompt": j.USER_PROMPT_TEMPLATE,
        "subject": j.SUBJECT_TEMPLATE,
        "followup_subject": j.FOLLOWUP_SUBJECT_TEMPLATE,
        "followup_1": j.FOLLOWUP_BODIES[1],
        "followup_2": j.FOLLOWUP_BODIES[2],
        "followup_3": j.FOLLOWUP_BODIES[3],
    }


def _sales_templates(icp: str) -> dict:
    from domains import sales_pitch as s

    system_prompt, subject, followup_subject, followup_bodies = s._resolve(icp)
    pitch = (
        s.CORPUS_CARBON_PITCH_TRADERS if icp == "traders"
        else s.CORPUS_CARBON_PITCH_PROFESSIONALS
    )
    return {
        "bio": pitch,
        "system_prompt": system_prompt,
        "user_prompt": s.USER_PROMPT_TEMPLATE,
        "subject": subject,
        "followup_subject": followup_subject,
        "followup_1": followup_bodies[1],
        "followup_2": followup_bodies[2],
        "followup_3": followup_bodies[3],
    }


def domain_template_content(domain: str) -> dict:
    """The eight template strings for a domain, read out of domains/*.py."""
    if domain == "job":
        return _job_templates()
    if domain == "sales":
        return _sales_templates("traders")
    if domain == "sales_professionals":
        return _sales_templates("professionals")
    raise ValueError(f"Unknown domain '{domain}'")


def seed_templates(conn) -> int:
    """Fills in any missing (domain, key) template rows. Never overwrites."""
    from app.services.templates import DOMAIN_KEYS

    inserted = 0
    for domain in DOMAIN_KEYS:
        content = domain_template_content(domain)
        for key, value in content.items():
            exists = conn.execute(
                "SELECT 1 FROM templates WHERE domain=? AND key=?", (domain, key)
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO templates (domain, key, content, updated_at) VALUES (?, ?, ?, ?)",
                (domain, key, value, now_iso()),
            )
            inserted += 1
    conn.commit()
    return inserted
