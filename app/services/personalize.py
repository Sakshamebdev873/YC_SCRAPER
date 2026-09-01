"""Turns a contact plus a template set into a subject and body.

Bodies are written by Google Gemini, reached through its OpenAI-compatible
endpoint — so the client object here is still the `openai` SDK's, and every
call site keeps the `client.chat.completions.create` shape.

Model defaults to the `gemini-flash-latest` alias so the app follows Google's
current flash release instead of pinning a version that ages. Override with
GEMINI_MODEL in .env (e.g. gemini-pro-latest for a stronger, slower writer).
"""

import os
from pathlib import Path

DEFAULT_MODEL = "gemini-flash-latest"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
TEMPERATURE = 0.3
MAX_TOKENS = 1600


def model_name() -> str:
    """Resolved at call time so .env loading order never matters."""
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def gemini_client():
    """Builds a Gemini-backed client from the environment, with the scraper
    settings module as a fallback for the key."""
    from openai import OpenAI

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        try:
            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from yc_scraper.settings import GEMINI_API_KEY as settings_key

            key = settings_key
        except Exception:
            key = ""
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set — add it to your .env file.")
    return OpenAI(api_key=key, base_url=BASE_URL)


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


def generate_body(client, templates: dict, contact: dict, model: str = None) -> str:
    resp = client.chat.completions.create(
        model=model or model_name(),
        messages=build_messages(templates, contact),
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    choice = resp.choices[0]
    content = choice.message.content
    if not (content or "").strip():
        raise RuntimeError(
            f"{model or model_name()} returned an empty body — "
            "the token budget may have gone entirely to reasoning."
        )
    # Gemini spends part of the budget thinking before it writes, so a tight
    # cap yields an email cut off mid-sentence. Fail the draft rather than
    # let half a sentence reach a founder; raise MAX_TOKENS if this recurs.
    if getattr(choice, "finish_reason", None) == "length":
        raise RuntimeError(
            f"{model or model_name()} hit the {MAX_TOKENS}-token cap and the body "
            "was cut off mid-sentence — raise MAX_TOKENS in personalize.py."
        )
    return content.strip()


def render_subject(templates: dict, contact: dict, round_num: int) -> str:
    key = "subject" if round_num == 0 else "followup_subject"
    return templates[key].format(company_name=contact.get("company_name", ""))


def render_followup_body(templates: dict, contact: dict, round_num: int) -> str:
    if round_num not in (1, 2, 3):
        raise ValueError(f"Follow-up round must be 1, 2 or 3 — got {round_num}")
    return templates[f"followup_{round_num}"].format(
        company_name=contact.get("company_name", "")
    )
