"""Turns a contact plus a template set into a subject and body.

Lifted from send_emails.py's personalize_email. Behaviour is unchanged:
same fallbacks, same model, same temperature and token cap.
"""

import os
from pathlib import Path

MODEL = "gpt-4o-mini"
TEMPERATURE = 0.3
MAX_TOKENS = 400


def openai_client():
    """Builds an OpenAI client from the environment, with the scraper settings
    module as a fallback for the key (matching send_emails.py today)."""
    from openai import OpenAI

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        try:
            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from yc_scraper.settings import OPENAI_API_KEY as settings_key

            key = settings_key
        except Exception:
            key = ""
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set — add it to your .env file.")
    return OpenAI(api_key=key)


def build_messages(templates: dict, contact: dict) -> list:
    founder_name = (contact.get("founder_name") or "").strip() or "there"
    first_name = founder_name.split()[0] if founder_name != "there" else "there"
    user_content = templates["user_prompt"].format(
        company_name=contact.get("company_name", ""),
        batch=contact.get("batch", ""),
        founder_first_name=first_name,
        company_description=(contact.get("company_description") or "").strip()
        or "an early-stage startup",
        company_website=contact.get("company_website", ""),
    )
    return [
        {"role": "system", "content": templates["system_prompt"]},
        {"role": "user", "content": user_content},
    ]


def generate_body(client, templates: dict, contact: dict, model: str = MODEL) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=build_messages(templates, contact),
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    return resp.choices[0].message.content.strip()


def render_subject(templates: dict, contact: dict, round_num: int) -> str:
    key = "subject" if round_num == 0 else "followup_subject"
    return templates[key].format(company_name=contact.get("company_name", ""))


def render_followup_body(templates: dict, contact: dict, round_num: int) -> str:
    if round_num not in (1, 2, 3):
        raise ValueError(f"Follow-up round must be 1, 2 or 3 — got {round_num}")
    return templates[f"followup_{round_num}"].format(
        company_name=contact.get("company_name", "")
    )
