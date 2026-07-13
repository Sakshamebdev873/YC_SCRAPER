"""Cold Email Sender — Gmail via SMTP

Domain-agnostic sender: pick a domain (what you're pitching and to whom) and
this script handles personalization, dedup, follow-up cadence, and sent-log
tracking the same way for all of them. Domains live in domains/ — see
domains/job_application.py (SDE Intern outreach to YC founders) and
domains/sales_pitch.py (SatsEarn.app pitch, currently against placeholder
leads) for what a domain provides.

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
import json
import os
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from domains import get_domain

# ── Config ────────────────────────────────────────────────────────────────────

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

OUTPUT_DIR = Path("output")
SENT_LOG = OUTPUT_DIR / "sent_log.json"

# Seconds between each send — keeps you under spam radar
SEND_DELAY = 30

# Minimum days before each follow-up round (Nick Singh: 3-4 / 4-5 / 5 days)
FOLLOWUP_MIN_DAYS = [0, 3, 4, 5]  # index = follow-up round number


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_sent_log() -> dict:
    """Returns {email: {"sent_at": iso_str, "followups": [iso_str, ...]}}"""
    if not SENT_LOG.exists():
        return {}
    raw = json.loads(SENT_LOG.read_text(encoding="utf-8"))
    # Migrate legacy format (list of strings → dict)
    if isinstance(raw, list):
        return {email: {"sent_at": None, "followups": []} for email in raw}
    return raw


def save_sent_log(log: dict):
    OUTPUT_DIR.mkdir(exist_ok=True)
    SENT_LOG.write_text(json.dumps(log, indent=2, sort_keys=True), encoding="utf-8")


def personalize_email(client: OpenAI, row: dict, system_prompt: str, user_prompt_template: str) -> str:
    founder_name = row.get("founder_name", "").strip() or "there"
    founder_first_name = founder_name.split()[0] if founder_name != "there" else "there"
    prompt = user_prompt_template.format(
        company_name=row["company_name"],
        batch=row.get("batch", ""),
        founder_first_name=founder_first_name,
        company_description=row.get("company_description", "").strip() or "an early-stage startup",
        company_website=row.get("company_website", ""),
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=400,
    )
    return resp.choices[0].message.content.strip()


def send_email(smtp: smtplib.SMTP, from_addr: str, to_addr: str, subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))
    smtp.sendmail(from_addr, to_addr, msg.as_string())


def connect_smtp(email: str, password: str) -> smtplib.SMTP:
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(email, password)
    return smtp


def dedupe_by_company(rows: list[dict]) -> list[dict]:
    """Keep only one contact per company — never email multiple people
    at the same company, since they'll compare notes and it reads as a mass blast.
    Prefers a CEO-titled founder; falls back to the first one listed."""
    best_by_company = {}
    for row in rows:
        company = row["company_name"]
        existing = best_by_company.get(company)
        if existing is None:
            best_by_company[company] = row
        elif "ceo" in row.get("founder_title", "").lower() and "ceo" not in existing.get("founder_title", "").lower():
            best_by_company[company] = row
    return list(best_by_company.values())


def followup_eligible(entry: dict, round_num: int) -> bool:
    """True if enough days have passed since the last contact for this follow-up round."""
    min_days = FOLLOWUP_MIN_DAYS[round_num]
    if round_num == 1:
        last_contact = entry.get("sent_at")
    else:
        followups = entry.get("followups", [])
        if len(followups) < round_num - 1:
            return False
        last_contact = followups[round_num - 2]
    if not last_contact:
        return False
    last_dt = datetime.fromisoformat(last_contact)
    return datetime.now() - last_dt >= timedelta(days=min_days)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send personalized cold emails")
    parser.add_argument("--domain", type=str, default="job", choices=["job", "sales"],
                         help="Which domain to send for: 'job' (SDE Intern outreach, default) or 'sales' (SatsEarn pitch)")
    parser.add_argument("--sales", action="store_true", help="Shorthand for --domain sales")
    parser.add_argument("--csv", type=Path, default=None, help="Path to founders CSV (job domain only)")
    parser.add_argument("--batch", type=str, default="", help="Only send to this batch (e.g. W27, W26) — job domain only")
    parser.add_argument("--icp", type=str, default="traders", choices=["traders", "professionals"],
                         help="Which ICP segment to target — sales domain only (default: traders)")
    parser.add_argument("--max", type=int, default=0, help="Max emails to send (0 = all / domain default)")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails, do not send")
    parser.add_argument("--test-email", type=str, default="", help="Redirect all sends to this address")
    parser.add_argument(
        "--followup", type=int, default=0, choices=[0, 1, 2, 3],
        help="Send follow-up round 1, 2, or 3 (default 0 = initial email)"
    )
    args = parser.parse_args()

    domain_name = "sales" if args.sales else args.domain
    domain = get_domain(domain_name)

    if not args.test_email:
        args.test_email = os.environ.get("TEST_EMAIL", "").strip() or getattr(domain, "DEFAULT_TEST_EMAIL", "")

    gmail_email = os.environ.get("GMAIL_EMAIL", "").strip()
    gmail_password = os.environ.get("GMAIL_PASSWORD", "").strip()
    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not args.dry_run:
        if not gmail_email or not gmail_password:
            print("ERROR: Set GMAIL_EMAIL and GMAIL_PASSWORD in your .env file.")
            print("  GMAIL_EMAIL=you@gmail.com")
            print("  GMAIL_PASSWORD=your-16-char-app-password")
            return

    if not openai_api_key:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from yc_scraper.settings import OPENAI_API_KEY as settings_key
            openai_api_key = settings_key
        except Exception:
            print("ERROR: OPENAI_API_KEY not set.")
            return

    client = OpenAI(api_key=openai_api_key)

    try:
        rows = domain.load_rows(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        return

    system_prompt, subject_template, followup_subject_template, followup_bodies = domain.get_prompts(args)

    sent_log = load_sent_log()

    is_followup = args.followup > 0
    round_num = args.followup

    if is_followup:
        queue = [
            r for r in rows
            if r.get("predicted_email")
            and r["founder_name"] not in ("Unknown", "")
            and r["predicted_email"] in sent_log
            and len(sent_log[r["predicted_email"]].get("followups", [])) < round_num
            and followup_eligible(sent_log[r["predicted_email"]], round_num)
        ]
    else:
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
        queue = dedupe_by_company(candidates)

    if args.max > 0 and domain_name != "sales":
        # Sales domain already applies --max when generating its placeholder rows.
        queue = queue[: args.max]

    mode_label = f"FOLLOW-UP #{round_num}" if is_followup else "INITIAL"
    domain_label = f"{domain_name.upper()}/{args.icp.upper()}" if domain_name == "sales" else domain_name.upper()
    print("=" * 60)
    print(f"  Cold Email Sender — {'DRY RUN' if args.dry_run else 'LIVE'} [{domain_label}] [{mode_label}]")
    print("=" * 60)
    print(f"  Total loaded    : {len(rows)}")
    print(f"  Already contacted: {len(sent_log)}")
    print(f"  Queue           : {len(queue)}")
    if not args.dry_run:
        print(f"  From            : {gmail_email}")
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
            smtp = connect_smtp(gmail_email, gmail_password)
            print("Connected.\n")
        except Exception as e:
            print(f"SMTP connection failed: {e}")
            print("Gmail requires an App Password (not your regular password).")
            print("Create one at: https://myaccount.google.com/apppasswords")
            print("  1. Enable 2FA first if not already on")
            print("  2. Create App Password → select 'Mail' → copy the 16-char code")
            print("  3. Re-run with that code as GMAIL_PASSWORD in .env")
            return

    sent_count = 0
    now_iso = datetime.now().isoformat(timespec="seconds")

    for i, row in enumerate(queue, 1):
        founder = row["founder_name"]
        company = row["company_name"]
        real_addr = row["predicted_email"]
        to_addr = args.test_email if args.test_email else real_addr

        if is_followup:
            subject = followup_subject_template.format(company_name=company)
            body = followup_bodies[round_num].format(company_name=company)
        else:
            subject = subject_template.format(company_name=company)
            try:
                body = personalize_email(client, row, system_prompt, domain.USER_PROMPT_TEMPLATE)
            except Exception as e:
                print(f"  GPT error: {e} — skipping")
                continue

        print(f"[{i}/{len(queue)}] {founder} @ {company} → {to_addr}")

        if args.dry_run:
            print(f"  Subject : {subject}")
            print("  Body ↓")
            for line in body.splitlines():
                print(f"    {line}")
            print()
            continue

        try:
            send_email(smtp, gmail_email, to_addr, subject, body)
            if not args.test_email:
                if is_followup:
                    entry = sent_log.setdefault(real_addr, {"sent_at": None, "followups": []})
                    entry.setdefault("followups", []).append(now_iso)
                else:
                    sent_log[real_addr] = {"sent_at": now_iso, "followups": []}
                save_sent_log(sent_log)
            sent_count += 1
            print(f"  Sent. ({sent_count} total)")
        except Exception as e:
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
        print(f"  Sent log: {SENT_LOG.absolute()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
