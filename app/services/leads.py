"""Synthetic sales leads.

domains/sales_pitch.py generates placeholder companies because there is no
real sales-lead list yet. This materializes them as contact rows so the
sales domains flow through the same queue, draft, and send path as the job
domain. Replace generate_placeholder_leads with a real lead loader once an
actual list exists — nothing downstream has to change.
"""

import random
from uuid import uuid4

from app.db import now_iso

SALES_DOMAIN_ICP = {"sales": "traders", "sales_professionals": "professionals"}


def generate_placeholder_leads(conn, domain: str, count: int) -> list:
    from domains import sales_pitch as s

    icp = SALES_DOMAIN_ICP.get(domain)
    if icp is None:
        raise ValueError(f"'{domain}' is not a sales domain")

    rng = random.Random()
    if icp == "traders":
        name_fn, topics, titles = s._random_trader_name, s._TRADER_TOPICS, s._TRADER_TITLES
    else:
        name_fn, topics, titles = s._random_firm_name, s._FIRM_TOPICS, s._FIRM_TITLES

    rows = []
    while len(rows) < count:
        description = rng.choice(topics)
        if icp == "professionals":
            description += " with 10+ employees"
        row = {
            "company_name": name_fn(rng),
            "batch": "N/A",
            "company_website": "",
            "company_description": description,
            "founder_name": rng.choice(s._FIRST_NAMES),
            "founder_title": rng.choice(titles),
            "predicted_email": f"{icp}-lead-{uuid4().hex[:8]}@example.local",
        }
        conn.execute(
            """INSERT INTO contacts (company_name, batch, company_website,
                                     company_description, founder_name, founder_title,
                                     predicted_email, domain, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
            (row["company_name"], row["batch"], row["company_website"],
             row["company_description"], row["founder_name"], row["founder_title"],
             row["predicted_email"], domain, now_iso()),
        )
        rows.append(row)
    conn.commit()
    return rows
