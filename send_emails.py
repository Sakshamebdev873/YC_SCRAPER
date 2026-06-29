"""
YC Founder Cold Email Sender — Gmail via SMTP

Usage:
    # Preview emails without sending (always start here)
    python send_emails.py --dry-run

    # Send initial emails to first 10 founders
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

Environment variables (set in .env or system):
    GMAIL_EMAIL      your Gmail address
    GMAIL_PASSWORD   App Password (create at myaccount.google.com/apppasswords)
    OPENAI_API_KEY   for personalizing initial emails
"""

import argparse
import csv
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

# ── Config ────────────────────────────────────────────────────────────────────

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

OUTPUT_DIR = Path("output")
SENT_LOG = OUTPUT_DIR / "sent_log.json"
DEFAULT_CSV = OUTPUT_DIR / "yc_founders_emails.csv"

# Seconds between each send — keeps you under spam radar
SEND_DELAY = 30

# Minimum days before each follow-up round (Nick Singh: 3-4 / 4-5 / 5 days)
FOLLOWUP_MIN_DAYS = [0, 3, 4, 5]  # index = follow-up round number

# ── Saksham's profile ─────────────────────────────────────────────────────────

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

# ── Initial email — target ~90 words (Nick Singh: 50-125, best ~100) ──────────

SYSTEM_PROMPT = """You write short cold emails from Saksham Arya to startup founders. Target length: 70-90 words total.

Output this EXACT template — only fill in [FIRST_NAME], [COMPANY_HOOK]:

---
Hi [FIRST_NAME],

[COMPANY_HOOK]

Quick snapshot:
- SatsEarn.app — live Bitcoin micro-rewards platform, real users across multiple countries, shipped solo
- 1st place, BrainBytes Hackathon 2025
- 4 remote internships (MERN, AI voice agents, full-stack React) — B.Tech CS, graduating 2027

Resume: https://drive.google.com/file/d/1Pyueb3pTLu_dBHOb69tHXq2fjrRaw47f/view?usp=drive_link | GitHub: https://github.com/Sakshamebdev873

Open to a 20-minute call this week?

Saksham Arya
+91 8738853746 | sakshamarya015@gmail.com
---

Rules:
- [FIRST_NAME]: the founder's first name only (e.g. "Alex", not "Alex Smith").
- [COMPANY_HOOK]: 1-2 sentences (under 35 words) specific to this company, tying to something Saksham has actually built. Lead with what the company is doing, then connect it to Saksham's relevant experience. No filler: no "I hope you are doing well", "I came across your company", "I am excited", or anything templated. Right tone: "Rebuilding payroll from scratch for gig workers is the kind of problem that sounds boring until you realise nobody has solved it — I've built MERN payment flows under similar constraints."
- Do NOT change any other wording, bullets, links, or the signature.
- Return only the email body. No subject line. No extra commentary."""

USER_PROMPT_TEMPLATE = """Write an application email for {company_name} (YC {batch}).

Founder name: {founder_name}
About {company_name}:
{company_description}
Website: {company_website}

Fill in [FIRST_NAME] with the founder's first name, and [COMPANY_HOOK] with 1-2 specific sentences about this company tied to Saksham's experience."""

# Subject line: credential-first (Nick Singh Tip #6)
SUBJECT_TEMPLATE = "SDE Intern @ {company_name} — BrainBytes 2025 + live product shipped"

# ── Follow-up templates — static, short nudges (Nick Singh Tip #7) ────────────

FOLLOWUP_SUBJECT_TEMPLATE = "Re: SDE Intern @ {company_name} — BrainBytes 2025 + live product shipped"

FOLLOWUP_BODIES = [
    None,  # index 0 unused (initial email uses SYSTEM_PROMPT above)
    # Round 1 — sent 3-4 days after initial
    """\
Just following up on my note below — still very interested in the SDE Intern role at {company_name}.

Happy to share more about my work if helpful.

Resume: https://drive.google.com/file/d/1Pyueb3pTLu_dBHOb69tHXq2fjrRaw47f/view?usp=drive_link

— Saksham Arya
+91 8738853746""",
    # Round 2 — sent 4-5 days after follow-up #1 (adds urgency/FOMO per Tip #3)
    """\
One more follow-up on the SDE Intern role at {company_name}. I'm actively interviewing at a few places but {company_name} is genuinely at the top of my list.

Would love a quick chat if there's any interest.

Resume: https://drive.google.com/file/d/1Pyueb3pTLu_dBHOb69tHXq2fjrRaw47f/view?usp=drive_link

— Saksham Arya
+91 8738853746""",
    # Round 3 — final nudge, sent 5 days after follow-up #2
    """\
Last follow-up — completely understand if the timing isn't right. If an SDE Intern opening ever comes up at {company_name}, I'd genuinely love to be considered.

Resume: https://drive.google.com/file/d/1Pyueb3pTLu_dBHOb69tHXq2fjrRaw47f/view?usp=drive_link

— Saksham Arya
+91 8738853746""",
]


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


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def personalize_email(client: OpenAI, row: dict) -> str:
    prompt = USER_PROMPT_TEMPLATE.format(
        company_name=row["company_name"],
        batch=row["batch"],
        founder_name=row.get("founder_name", "").strip() or "there",
        company_description=row.get("company_description", "").strip() or "an early-stage startup",
        company_website=row.get("company_website", ""),
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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
    parser = argparse.ArgumentParser(description="Send personalized cold emails to YC founders")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to founders CSV")
    parser.add_argument("--max", type=int, default=0, help="Max emails to send (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails, do not send")
    parser.add_argument("--test-email", type=str, default="", help="Redirect all sends to this address")
    parser.add_argument(
        "--followup", type=int, default=0, choices=[0, 1, 2, 3],
        help="Send follow-up round 1, 2, or 3 (default 0 = initial email)"
    )
    args = parser.parse_args()

    if not args.test_email:
        args.test_email = os.environ.get("TEST_EMAIL", "").strip()

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

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}")
        print("Run the scraper first: python run_scraper.py --batch W26 --max 50")
        return

    rows = load_csv(args.csv)
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
        queue = [
            r for r in rows
            if r.get("predicted_email")
            and r["founder_name"] not in ("Unknown", "")
            and r["predicted_email"] not in sent_log
        ]

    if args.max > 0:
        queue = queue[: args.max]

    mode_label = f"FOLLOW-UP #{round_num}" if is_followup else "INITIAL"
    print("=" * 60)
    print(f"  Cold Email Sender — {'DRY RUN' if args.dry_run else 'LIVE'} [{mode_label}]")
    print("=" * 60)
    print(f"  Total in CSV    : {len(rows)}")
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
            print("Nothing to send — all founders already emailed or no predicted emails found.")
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
            subject = FOLLOWUP_SUBJECT_TEMPLATE.format(company_name=company)
            body = FOLLOWUP_BODIES[round_num].format(company_name=company)
        else:
            subject = SUBJECT_TEMPLATE.format(company_name=company)
            try:
                body = personalize_email(client, row)
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
