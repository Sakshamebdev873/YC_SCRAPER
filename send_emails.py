"""Cold Email Sender — Gmail via SMTP

Domain-agnostic sender: pick a domain (what you're pitching and to whom) and
this script handles personalization, dedup, follow-up cadence, and send
tracking the same way for all of them. Domains live in domains/ — see
domains/job_application.py (SDE Intern outreach to YC founders) and
domains/sales_pitch.py (SatsEarn.app pitch, currently against placeholder
leads) for what a domain provides. All state now lives in output/app.db
(SQLite) instead of output/sent_log.json.

Usage:
    # Preview emails without sending (always start here)
    python send_emails.py --dry-run

    # Send initial emails to first 10 founders (job domain, default)
    python send_emails.py --max 10

    # Send all unsent founders
    python send_emails.py

    # Send follow-up #1 (run 3-4 days after initial)
    python send_emails.py --followup 1

    # Send follow-up #2 (run 4-5 days after follow-up #1)
    python send_emails.py --followup 2

    # Send follow-up #3 — final nudge (run 5 days after follow-up #2)
    python send_emails.py --followup 3

    # Use a different CSV
    python send_emails.py --csv output/yc_founders_emails.csv

    # Sales domain: pitch SatsEarn.app to placeholder leads, routed to a
    # fixed test inbox until a real sales-lead source is wired up
    python send_emails.py --sales --dry-run
    python send_emails.py --sales

Environment variables (set in .env or system):
    GMAIL_EMAIL      your Gmail address
    GMAIL_PASSWORD   App Password (create at myaccount.google.com/apppasswords)
    OPENAI_API_KEY   for personalizing initial emails
"""

import argparse
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.db import get_conn, init_db, now_iso
from app.seed import DEFAULT_CSV, seed_all
from app.services.drafts import upsert_draft, update_draft
from app.services.leads import SALES_DOMAIN_ICP, generate_placeholder_leads
from app.services.mailer import APP_PASSWORD_HELP, connect_smtp, gmail_credentials, send_email
from app.services.personalize import (
    generate_body, openai_client, render_followup_body, render_subject,
)
from app.services.queue import eligible_followup, eligible_initial
from app.services.templates import get_templates

SEND_DELAY = 30

DEFAULT_TEST_EMAIL_BY_DOMAIN = {
    "job": "",
    "sales": "vinodarya344@gmail.com",
    "sales_professionals": "vinodarya344@gmail.com",
}

ICP_DEFAULT_COUNTS = {"traders": 2, "professionals": 5}


def db_domain_for(args) -> str:
    name = "sales" if args.sales else args.domain
    if name != "sales":
        return "job"
    return "sales_professionals" if args.icp == "professionals" else "sales"


def record_send(conn, contact, draft_id, round_num, to_addr, test_mode, error=None):
    conn.execute(
        """INSERT INTO sends (contact_id, draft_id, round, to_addr, real_addr,
                              sent_at, test_mode, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (contact["id"], draft_id, round_num, to_addr, contact["predicted_email"],
         now_iso(), 1 if test_mode else 0, error),
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Send personalized cold emails")
    parser.add_argument("--domain", type=str, default="job", choices=["job", "sales"],
                        help="Which domain to send for: 'job' (SDE Intern outreach, default) or 'sales'")
    parser.add_argument("--sales", action="store_true", help="Shorthand for --domain sales")
    parser.add_argument("--csv", type=Path, default=None, help="Path to founders CSV to import first (job domain only)")
    parser.add_argument("--batch", type=str, default="", help="Only send to this batch (e.g. W26) — job domain only")
    parser.add_argument("--icp", type=str, default="traders", choices=["traders", "professionals"],
                        help="Which ICP segment to target — sales domain only (default: traders)")
    parser.add_argument("--max", type=int, default=0, help="Max emails to send (0 = all / domain default)")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails, do not send")
    parser.add_argument("--test-email", type=str, default="", help="Redirect all sends to this address")
    parser.add_argument("--followup", type=int, default=0, choices=[0, 1, 2, 3],
                        help="Send follow-up round 1, 2, or 3 (default 0 = initial email)")
    args = parser.parse_args()

    import os

    domain = db_domain_for(args)
    is_followup = args.followup > 0
    round_num = args.followup

    conn = get_conn()
    init_db(conn)
    seed_all(conn, csv_path=args.csv or DEFAULT_CSV)

    if not args.test_email:
        args.test_email = (
            os.environ.get("TEST_EMAIL", "").strip()
            or DEFAULT_TEST_EMAIL_BY_DOMAIN[domain]
        )

    if domain in SALES_DOMAIN_ICP and not is_followup:
        icp = SALES_DOMAIN_ICP[domain]
        count = args.max if args.max > 0 else ICP_DEFAULT_COUNTS[icp]
        generate_placeholder_leads(conn, domain, count)

    gmail = ("", "")
    if not args.dry_run:
        try:
            gmail = gmail_credentials()
        except RuntimeError as e:
            print(f"ERROR: {e}")
            return

    try:
        client = openai_client()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return

    templates = get_templates(conn, domain)
    limit = args.max if args.max > 0 else 0
    if is_followup:
        queue = eligible_followup(conn, domain=domain, round_num=round_num, limit=limit)
    else:
        queue = eligible_initial(conn, domain=domain, batch=args.batch, limit=limit)

    mode_label = f"FOLLOW-UP #{round_num}" if is_followup else "INITIAL"
    print("=" * 60)
    print(f"  Cold Email Sender — {'DRY RUN' if args.dry_run else 'LIVE'} [{domain.upper()}] [{mode_label}]")
    print("=" * 60)
    print(f"  Queue           : {len(queue)}")
    if not args.dry_run:
        print(f"  From            : {gmail[0]}")
        if args.test_email:
            print(f"  *** TEST MODE   : all emails → {args.test_email} ***")
        print(f"  Delay between   : {SEND_DELAY}s")
    print("=" * 60)
    print()

    if not queue:
        if is_followup:
            print(f"No eligible follow-ups for round #{round_num}. Either not enough days have passed or all already sent.")
        else:
            print("Nothing to send — all contacts already emailed or no predicted emails found.")
        return

    smtp = None
    if not args.dry_run:
        print("Connecting to Gmail SMTP...")
        try:
            smtp = connect_smtp(*gmail)
            print("Connected.\n")
        except Exception as e:
            print(f"SMTP connection failed: {e}")
            print(APP_PASSWORD_HELP)
            return

    sent_count = 0
    for i, contact in enumerate(queue, 1):
        to_addr = args.test_email if args.test_email else contact["predicted_email"]
        subject = render_subject(templates, contact, round_num)
        if is_followup:
            body = render_followup_body(templates, contact, round_num)
        else:
            try:
                body = generate_body(client, templates, contact)
            except Exception as e:
                print(f"  GPT error: {e} — skipping")
                continue

        print(f"[{i}/{len(queue)}] {contact['founder_name']} @ {contact['company_name']} → {to_addr}")

        if args.dry_run:
            print(f"  Subject : {subject}")
            print("  Body ↓")
            for line in body.splitlines():
                print(f"    {line}")
            print()
            continue

        draft_id = upsert_draft(conn, contact["id"], domain, round_num, subject, body,
                                status="approved")
        try:
            send_email(smtp, gmail[0], to_addr, subject, body)
            record_send(conn, contact, draft_id, round_num, to_addr, bool(args.test_email))
            update_draft(conn, draft_id, status="sent")
            sent_count += 1
            print(f"  Sent. ({sent_count} total)")
        except Exception as e:
            record_send(conn, contact, draft_id, round_num, to_addr, bool(args.test_email), str(e))
            update_draft(conn, draft_id, status="failed", error=str(e))
            print(f"  Send failed: {e}")

        if i < len(queue):
            print(f"  Waiting {SEND_DELAY}s...")
            time.sleep(SEND_DELAY)

    if smtp:
        smtp.quit()

    print()
    print("=" * 60)
    if args.dry_run:
        print(f"  DRY RUN complete. {len(queue)} emails previewed.")
        print("  Re-run without --dry-run to actually send.")
    else:
        print(f"  Done. {sent_count}/{len(queue)} emails sent.")
    print("=" * 60)


if __name__ == "__main__":
    main()
