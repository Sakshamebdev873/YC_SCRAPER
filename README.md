# YC Founder Cold Email Applier

An automated pipeline to scrape Y Combinator startup founders and send them highly personalized, AI-generated cold emails. 

This project consists of two main components:
1. **YC Scraper (`yc_scraper`)**: Scrapes Y Combinator companies and founders via the Algolia API and YC company pages, then predicts founder emails using OpenAI ChatGPT (`gpt-4o-mini`).
2. **Cold Email Sender (`send_emails.py`)**: Reads the scraped CSV data, generates personalized emails based on your profile (Saksham Arya) and the company's description using OpenAI, and sends them via Gmail/Outlook SMTP.

---

## Features

### 1. Scraper (`run_scraper.py`)
- **Algolia API Integration**: Bypasses traditional scraping blocks by querying the same Algolia index YC uses (`YCCompany_production`).
- **Batch Filtering**: easily target specific cohorts using shortcodes (e.g., `W25`, `S25`, `F26`) or run against default recent batches.
- **Deep Data Extraction**: Pulls founder names, titles, LinkedIn, and Twitter profiles from individual company pages (handling Inertia.js embedded data).
- **AI Email Prediction**: Uses `gpt-4o-mini` to intelligently predict founder email addresses based on their name and company domain (e.g., guessing `firstname@domain`).
- **CSV Export**: Outputs a clean dataset to `output/yc_founders_emails.csv`.

### 2. Email Sender (`send_emails.py`)
- **AI Personalization**: Uses `gpt-4o-mini` to write a formal, warm, and highly personalized cold email. It blends your specific background (B.Tech student, creator of SatsEarn.app, Hackathon winner) with the company's exact description.
- **Dry-Run Mode**: Preview exactly what emails will look like in the console before actually sending anything (`--dry-run`).
- **Rate Limiting & Safety**: Built-in delays (30 seconds between emails) to avoid spam filters.
- **Duplicate Prevention**: Keeps a `sent_log.json` state file to ensure you never accidentally email the same founder twice.
- **SMTP Integration**: Works via standard SMTP (configured for Gmail/Google Workspace via App Passwords).

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
   Open `yc_scraper/settings.py` and set your OpenAI API key:
   ```python
   OPENAI_API_KEY = "sk-proj-..." 
   ```
   Alternatively, set it in your environment variables.

---

## Usage Guide

### Phase 1: Scrape Founders
Run the scraper to generate your target list.

```bash
# Scrape default recent batches (W26, SP26, S25, F25) with a limit of 20 companies
python run_scraper.py

# Scrape a specific batch (e.g., Winter 2025) and limit to 50 companies
python run_scraper.py --batch W25 --max 50

# Scrape all companies (Warning: Takes a long time and uses many OpenAI tokens)
python run_scraper.py --all
```
*Results are saved to `output/yc_founders_emails.csv`.*

### Phase 2: Send Personalized Emails
Set up your Gmail SMTP credentials as environment variables. **Note:** You must use an [App Password](https://myaccount.google.com/apppasswords) if 2FA is enabled.

```powershell
$env:GMAIL_EMAIL="your.email@gmail.com"
$env:GMAIL_PASSWORD="your_app_password"
```

**Always preview first:**
```bash
python send_emails.py --dry-run
```

**Send to a limited batch:**
```bash
# Send emails to the first 10 founders in the queue
python send_emails.py --max 10
```

**Send to everyone:**
```bash
# Will skip anyone already in output/sent_log.json
python send_emails.py
```

---

## Customizing Your Profile
If you want to modify the email contents, open `send_emails.py` and edit the `CANDIDATE_BIO` variable. This bio is fed directly to the AI to construct the email body.

## Disclaimer
Please ensure you comply with anti-spam regulations (like CAN-SPAM) when sending cold emails. Keep your sending volume low and targeted.
