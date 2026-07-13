"""Job-application domain — cold emails pitching Saksham Arya for an SDE Intern
role at YC-founder companies scraped by yc_scraper.
"""

import csv
from pathlib import Path

from yc_scraper.spiders.yc_spider import BATCH_NAME_MAP

DEFAULT_CSV = Path("output") / "yc_founders_emails.csv"

# No override — respects --test-email / TEST_EMAIL env as normal.
DEFAULT_TEST_EMAIL = ""

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

SYSTEM_PROMPT_TEMPLATE = """You write short cold emails from Saksham Arya to startup founders, applying for an SDE Intern role. These must NOT read like a mail-merged template — no bullet lists, no "quick snapshot" section, no keyword-stuffed credential dump. Write like a specific person who actually looked at this company and has a real reason to write in, not like every founder is getting the same email.

Write the email as flowing prose (no headers, no bullets), following this shape:

1. Opening (2-3 sentences): say something specific and real about the problem [company] is working on — an actual observation, not a generic compliment ("cool project", "impressive team"). Then connect it naturally to ONE relevant thing Saksham has built (pick whichever fits best from the bio below — don't list more than one or two).
2. Optionally one short added-context sentence (e.g. hackathon win, graduation year) — only include it if it strengthens the pitch; skip if it'd feel bolted on.
3. On its own line: "Resume: https://drive.google.com/file/d/1Pyueb3pTLu_dBHOb69tHXq2fjrRaw47f/view?usp=drive_link | GitHub: https://github.com/Sakshamebdev873"
4. A low-key, specific closing ask. Vary the phrasing across emails — do not default to "Open to a 20-minute call this week?" every time. Something like "Are you hiring for anything on the eng side right now?" or "Worth a quick call?" or "Any chance there's room for an intern this cycle?".
5. Sign-off, exactly:
Saksham Arya
+91 8738853746 | sakshamarya015@gmail.com

Saksham's background (pick 1-2 relevant details — never dump all of it):
{bio}

Hard rules:
- 70-100 words total.
- Never use these phrases: "I hope this email finds you", "I came across your company", "I'm excited/passionate about", "reaching out", "opportunity", "I'd love the chance".
- No bullet points, no markdown formatting, no headers.
- Should read like one engineer emailing another, not a job application form.
- Return only the email body — no subject line, no commentary."""

SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.format(bio=CANDIDATE_BIO)

USER_PROMPT_TEMPLATE = """Write the email for {company_name} (YC {batch}).

Founder's first name: {founder_first_name}
About {company_name}: {company_description}
Website: {company_website}

Open with "Hi {founder_first_name}," then write the rest of the email per the system instructions."""

# Subject line: natural, not keyword-stuffed
SUBJECT_TEMPLATE = "Question about the SDE Intern role at {company_name}"

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


def get_prompts(args):
    """Returns (system_prompt, subject_template, followup_subject_template, followup_bodies).

    This domain has no per-run variants, so it ignores args and always
    returns the same static content.
    """
    return SYSTEM_PROMPT, SUBJECT_TEMPLATE, FOLLOWUP_SUBJECT_TEMPLATE, FOLLOWUP_BODIES


def load_rows(args) -> list[dict]:
    """Loads founder rows from the scraped CSV, optionally filtered by YC batch."""
    csv_path = args.csv or DEFAULT_CSV
    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV not found: {csv_path}\n"
            f"Run the scraper first: python run_scraper.py --batch W26 --max 50"
        )

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.batch:
        batch_filter = BATCH_NAME_MAP.get(args.batch.upper(), args.batch)
        rows = [r for r in rows if r.get("batch", "").strip() == batch_filter]
        if not rows:
            raise ValueError(f"No rows found for batch '{args.batch}' (looked for '{batch_filter}').")

    return rows
