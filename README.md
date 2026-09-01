# Cold Email Applier

An automated pipeline to scrape Y Combinator startup founders and send them personalized, AI-generated cold emails — for SDE intern outreach, or for pitching Corpus Carbon & Chemicals (corpuscarbon.com) as a sales domain.

This project consists of four main components:
1. **YC Scraper (`yc_scraper`)**: Scrapes Y Combinator companies and founders via the Algolia API and YC company pages, then predicts founder emails using OpenAI ChatGPT (`gpt-4o-mini`).
2. **Domains (`domains/`)**: Each domain owns its own pitch content (bio/system prompt/subject/follow-ups) and knows how to load its own list of target rows. Two domains ship today:
   - `job_application` (default) — SDE Intern outreach to YC founders, reading from the scraped CSV.
   - `sales_pitch` (`--sales`) — pitches Corpus Carbon & Chemicals' activated carbon products, on behalf of Karan. Two ICP segments selected with `--icp`: `traders` (activated carbon traders/distributors, default) and `professionals` (law/accounting firm owners or marketing directors, 10+ employees — pitched office HVAC/odor-control filter media). There's no real sales-lead list yet, so it generates a handful of random placeholder companies per ICP each run and routes every send to a fixed test inbox (`vinodarya344@gmail.com`) until a real lead source is wired up.
3. **Cold Email Sender (`send_emails.py`)**: Domain-agnostic — asks the selected domain for rows and prompts, then handles personalization, company-based dedup, and the 3-round follow-up cadence the same way regardless of domain. State (who has been contacted, when, and in which round) lives in `output/app.db` rather than `sent_log.json`; the old JSON log is migrated on first run and left on disk as a backup.
4. **Web UI (`app/`, `frontend/`)**: A local dashboard over the same database — contacts, template editing with live preview, per-draft review, sending with live progress, and follow-ups. Run it with `python app.py`. See [Web UI](#web-ui) below.

---

## Features

### 1. Scraper (`run_scraper.py`)
- **Algolia API Integration**: Bypasses traditional scraping blocks by querying the same Algolia index YC uses (`YCCompany_production`).
- **Batch Filtering**: easily target specific cohorts using shortcodes (e.g., `W26`, `SP26`, `SU26`, `W25`, `SP25`, `S25`, `F25`) or run against the default recent batches (W26 + SP26 + S25 + F25).
- **Deep Data Extraction**: Pulls founder names, titles, LinkedIn, and Twitter profiles from individual company pages (handling Inertia.js embedded data).
- **AI Email Prediction**: Uses `gpt-4o-mini` to intelligently predict founder email addresses based on their name and company domain (e.g., guessing `firstname@domain`).
- **CSV Export**: Outputs a clean dataset to `output/yc_founders_emails.csv`.

### 2. Email Sender (`send_emails.py`)
- **AI Personalization**: Uses `gpt-4o-mini` to write short (70-100 word), flowing-prose cold emails from a natural-language prompt (no rigid mail-merge templates) — blending one relevant piece of your background with something specific about the company.
- **Follow-up Sequence**: Built-in 3-round follow-up cadence (`--followup 1/2/3`, spaced 3-4 / 4-5 / 5 days apart) with static nudge templates, tracked per-recipient in `sent_log.json`.
- **Company-Based Deduplication**: Only ever emails one founder per company (preferring the CEO if there's a choice), so co-founders never compare notes on a mass blast.
- **Dry-Run Mode**: Preview exactly what emails will look like in the console before actually sending anything (`--dry-run`).
- **Rate Limiting & Safety**: Built-in delays (30 seconds between emails) to avoid spam filters.
- **Duplicate Prevention**: Keeps a `sent_log.json` state file (sent timestamp + follow-up history) to ensure you never accidentally re-email the same founder.
- **SMTP Integration**: Works via standard SMTP (configured for Gmail via App Passwords).

---

## Installation

1. **Clone & Environment**
   ```bash
   git clone <repo-url>
   cd "Job_email applier"
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   *Core dependencies: `scrapy`, `openai`*

3. **Environment Setup**
   You need an OpenAI API Key for both the scraper and the sender.
   Create a `.env` file in the root directory and add your keys:
   ```env
   OPENAI_API_KEY="sk-proj-..."
   GMAIL_EMAIL="your.email@gmail.com"
   GMAIL_PASSWORD="your_app_password"
   ```

---

## Usage Guide

### Phase 1: Scrape Founders
Run the scraper to generate your target list.

```bash
# Scrape default recent batches (W26, SP26, S25, F25) with a limit of 20 companies
python run_scraper.py

# Scrape a specific batch (e.g., Winter 2025) and limit to 50 companies
python run_scraper.py --batch W25 --max 50

# Scrape all companies in a batch (Warning: Takes a long time and uses many OpenAI tokens)
python run_scraper.py --batch W26 --all
```
*Results are saved to `output/yc_founders_emails.csv`.*

### Phase 2: Send Personalized Emails
Set up your Gmail SMTP credentials in the `.env` file. **Note:** You must use an [App Password](https://myaccount.google.com/apppasswords) if 2FA is enabled.

**Always preview first:**
```bash
python send_emails.py --dry-run
```

**Send initial emails (limited or unlimited):**
```bash
# Send emails to the first 10 founders in the queue
python send_emails.py --max 10

# Send to everyone eligible (skips anyone already in output/sent_log.json,
# and skips companies where any founder was already contacted)
python send_emails.py

# Restrict to one scraped batch
python send_emails.py --batch W26
```

**Send follow-ups** (run these a few days apart, per founder already contacted):
```bash
python send_emails.py --followup 1   # 3-4 days after the initial email
python send_emails.py --followup 2   # 4-5 days after follow-up #1
python send_emails.py --followup 3   # 5 days after follow-up #2 — final nudge
```

Other useful flags: `--csv <path>` to point at a different CSV, `--test-email you@example.com` to redirect all sends to one inbox while testing.

### Sales domain: pitching Corpus Carbon & Chemicals
```bash
# Preview — generates random placeholder companies/topics each run
python send_emails.py --sales --icp traders --dry-run
python send_emails.py --sales --icp professionals --dry-run

# Send for real — routed to vinodarya344@gmail.com by default (no real lead
# list yet); pass --test-email to route elsewhere instead
python send_emails.py --sales --icp traders
```
`--icp` defaults to `traders` if omitted. Default placeholder batch size is 2 leads for `traders` and 5 for `professionals` (override with `--max`). Replace `domains/sales_pitch.py`'s `load_rows()` with a real lead loader (CSV/API) once an actual sales-lead list exists — everything else (personalization, dedup, follow-ups, sent-log tracking) already works against it unchanged.

---

## Web UI

A local dashboard covering the whole loop: contacts, template finalising with
live preview, per-draft review, sending with live progress, and follow-ups.

```bash
# one-time: install backend deps and build the frontend
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# run it
python app.py
```

Opens `http://127.0.0.1:8000` — localhost only, no auth, never exposed.

**Screens**
- **Dashboard** — contacts, contacted, pending/approved drafts, follow-ups due, recent runs.
- **Contacts** — search and filter all scraped founders, fix a wrong predicted email inline, skip someone, or scrape a new batch.
- **Templates** — edit the bio, system prompt, user prompt, subject, and the three follow-up bodies per domain. *Preview* renders with the text currently in the editor, saved or not, so you can iterate against a real founder before committing. Every save archives the previous version; Restore brings one back.
- **Compose** — pick domain, batch, round, and a limit; generate drafts; edit, approve, reject, or regenerate each one.
- **Send** — approved drafts only. Test mode is on by default and routes everything to `TEST_EMAIL`; turning it off raises a red banner. Live progress, and a Stop button that takes effect between emails.
- **Follow-ups** — who is past the 3 / 4 / 5-day threshold for rounds 1, 2, and 3. Nothing sends automatically; you generate drafts and they go through the same review and send path.

**Frontend development**

```bash
python -m uvicorn "app.main:create_app" --factory --port 8000   # terminal 1
cd frontend && npm run dev                                       # terminal 2, port 5173
```

### State

State lives in `output/app.db` (SQLite), seeded on first run from
`output/yc_founders_emails.csv` and `output/sent_log.json`. Both files are left
untouched as backups. Templates seed from `domains/*.py` and are editable from
the UI thereafter — the Python modules stay as the original content and the
first-run source. The CLI (`send_emails.py`) reads and writes the same database,
so the UI and the CLI never disagree about who has been contacted.

### Tests

```bash
python -m pytest tests/ -v
```

No test opens a socket to Gmail or OpenAI.

---

## Customizing Your Profile
Each domain's content lives in its own module under `domains/`:
- `domains/job_application.py` — `CANDIDATE_BIO`, `SYSTEM_PROMPT_TEMPLATE` (tone/structure/word count/banned phrases), `FOLLOWUP_BODIES` for the SDE Intern outreach.
- `domains/sales_pitch.py` — `CORPUS_CARBON_PITCH_TRADERS` / `CORPUS_CARBON_PITCH_PROFESSIONALS`, per-ICP system prompts and follow-up bodies, `SIGN_OFF`, plus the placeholder lead generator.

`send_emails.py` itself only orchestrates sending — it doesn't need to change when you edit a domain's content or add a new domain (register it in `domains/__init__.py`).

## Disclaimer
Please ensure you comply with anti-spam regulations (like CAN-SPAM) when sending cold emails. Keep your sending volume low and targeted.
