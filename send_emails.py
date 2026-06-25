"""
YC Founder Cold Email Sender — Outlook/Hotmail via SMTP

Usage:
    # Preview emails without sending (always start here)
    python send_emails.py --dry-run

    # Send to first 10 founders
    python send_emails.py --max 10

    # Send all unsent founders
    python send_emails.py

    # Use a different CSV
    python send_emails.py --csv output/yc_founders_emails.csv

Environment variables (set in .env or system):
    GMAIL_EMAIL    your outlook/hotmail address
    GMAIL_PASSWORD your password (use App Password if 2FA is on)
    OPENAI_API_KEY   for personalizing emails (already set in settings)
    YOUR_NAME        your full name for the email signature
    YOUR_GITHUB      your GitHub profile URL
    YOUR_LINKEDIN    your LinkedIn profile URL
"""

import argparse
import csv
import json
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

OUTPUT_DIR = Path("output")
SENT_LOG = OUTPUT_DIR / "sent_log.json"
DEFAULT_CSV = OUTPUT_DIR / "yc_founders_emails.csv"

# Seconds between each send — keeps you under spam radar
SEND_DELAY = 30  # 30s = ~120 emails/hour max

# ── Saksham's profile (pre-filled from resume + LinkedIn) ────────────────────

DEFAULT_YOUR_NAME = "Saksham Arya"
DEFAULT_YOUR_GITHUB = "https://github.com/Sakshamebdev873"
DEFAULT_YOUR_LINKEDIN = "https://www.linkedin.com/in/saksham-arya-b9a793330/"

CANDIDATE_BIO = """
- 2nd-year B.Tech CSE student (graduating 2027), Bipin Tripathi Kumaoun Institute of Technology
- Built SatsEarn.app — a live Bitcoin micro-rewards platform with real active users across multiple countries; zero KYC, Lightning Network payouts, AI-powered bot prevention
- Won 1st place at BrainBytes Hackathon 2025
- 4 remote internships: React.js dev, Full Stack (MERN), creative frontend with GSAP animations, AI voice agent for real estate using Vapi API
- Stack: MERN (MongoDB, Express, React, Node.js), Supabase, Tailwind CSS, GSAP, Framer Motion, Gemini AI
- Built AI-powered products: Nayamitrr (legal chatbot with document generation), Developer Mate (AI mentor for beginner devs)
- GitHub: https://github.com/Sakshamebdev873
- LinkedIn: https://www.linkedin.com/in/saksham-arya-b9a793330/
""".strip()

# ── Email template prompt ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You write professional cold emails from Saksham Arya, a 2nd-year CS student seeking an internship or SDE role at a YC startup.

Rules:
- Use a formal but warm tone — not robotic, not overly casual
- Structure: greeting → 1 line about the company → 1 line about Saksham → bullet list of 3-4 projects → 1 line on why this company specifically → closing
- Bullet points must use plain hyphens (-), not markdown or special characters
- Mention SatsEarn.app as a live platform with real active users — do NOT mention specific user counts or country numbers
- End with: "Thank you for your time. I would love the opportunity to contribute and grow with your team."
- After the closing line add this exact signature block (copy it verbatim):

Best regards,
Saksham Arya
+91 8738853746
sakshamarya015@gmail.com
GitHub: https://github.com/Sakshamebdev873
LinkedIn: https://www.linkedin.com/in/saksham-arya-b9a793330/

- Return only the email body. No subject line. No placeholders."""

USER_PROMPT_TEMPLATE = """Write a cold email from Saksham Arya to {founder_name}, co-founder of {company_name} (YC {batch}).

About {company_name}:
{company_description}
Website: {company_website}

Saksham's background:
{candidate_bio}

Write the full email body."""

SUBJECT_TEMPLATE = "Internship / SDE Interest — {company_name} | Full Stack Developer"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_sent_log() -> set:
    if SENT_LOG.exists():
        return set(json.loads(SENT_LOG.read_text(encoding="utf-8")))
    return set()


def save_sent_log(sent: set):
    OUTPUT_DIR.mkdir(exist_ok=True)
    SENT_LOG.write_text(json.dumps(sorted(sent), indent=2), encoding="utf-8")


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def personalize_email(client: OpenAI, row: dict) -> str:
    prompt = USER_PROMPT_TEMPLATE.format(
        founder_name=row["founder_name"],
        company_name=row["company_name"],
        batch=row["batch"],
        company_description=row.get("company_description", "").strip() or "an early-stage startup",
        company_website=row.get("company_website", ""),
        candidate_bio=CANDIDATE_BIO,
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=300,
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send personalized cold emails to YC founders")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to founders CSV")
    parser.add_argument("--max", type=int, default=0, help="Max emails to send (0 = all unsent)")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails, do not send")
    args = parser.parse_args()

    # ── Credentials ──
    outlook_email = os.environ.get("GMAIL_EMAIL", "").strip()
    outlook_password = os.environ.get("GMAIL_PASSWORD", "").strip()
    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not args.dry_run:
        if not outlook_email or not outlook_password:
            print("ERROR: Set GMAIL_EMAIL and GMAIL_PASSWORD environment variables.")
            print("  $env:GMAIL_EMAIL='you@outlook.com'")
            print("  $env:GMAIL_PASSWORD='yourpassword'")
            return

    if not openai_api_key:
        # Fall back to settings.py key
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from yc_scraper.settings import OPENAI_API_KEY as settings_key
            openai_api_key = settings_key
        except Exception:
            print("ERROR: OPENAI_API_KEY not set.")
            return

    client = OpenAI(api_key=openai_api_key)

    # ── Load data ──
    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}")
        print("Run the scraper first: python run_scraper.py --batch W26 --max 50")
        return

    rows = load_csv(args.csv)
    sent_log = load_sent_log()

    # Filter: skip unknowns, already sent, missing emails
    queue = [
        r for r in rows
        if r.get("predicted_email")
        and r["founder_name"] not in ("Unknown", "")
        and r["predicted_email"] not in sent_log
    ]

    if args.max > 0:
        queue = queue[: args.max]

    print("=" * 60)
    print(f"  Cold Email Sender — {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)
    print(f"  Total in CSV   : {len(rows)}")
    print(f"  Already sent   : {len(sent_log)}")
    print(f"  Queue to send  : {len(queue)}")
    if not args.dry_run:
        print(f"  From           : {outlook_email}")
        print(f"  Delay between  : {SEND_DELAY}s")
    print("=" * 60)
    print()

    if not queue:
        print("Nothing to send — all founders already emailed or no predicted emails found.")
        return

    # ── Connect SMTP (skip in dry-run) ──
    smtp = None
    if not args.dry_run:
        print("Connecting to Outlook SMTP...")
        try:
            smtp = connect_smtp(outlook_email, outlook_password)
            print("Connected.\n")
        except Exception as e:
            print(f"SMTP connection failed: {e}")
            print("Gmail requires an App Password (not your regular password).")
            print("Create one at: https://myaccount.google.com/apppasswords")
            print("  1. Enable 2FA first if not already on")
            print("  2. Create App Password -> select 'Mail' -> copy the 16-char code")
            print("  3. Re-run with that code as GMAIL_PASSWORD")
            return

    # ── Send loop ──
    sent_count = 0
    for i, row in enumerate(queue, 1):
        founder = row["founder_name"]
        company = row["company_name"]
        to_addr = row["predicted_email"]
        subject = SUBJECT_TEMPLATE.format(company_name=company)

        print(f"[{i}/{len(queue)}] {founder} @ {company} <{to_addr}>")

        try:
            body = personalize_email(client, row)
        except Exception as e:
            print(f"  GPT error: {e} — skipping")
            continue

        if args.dry_run:
            print(f"  Subject: {subject}")
            print("  --- Body preview ---")
            for line in body.splitlines():
                print(f"  {line}")
            print()
            continue

        try:
            send_email(smtp, outlook_email, to_addr, subject, body)
            sent_log.add(to_addr)
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
