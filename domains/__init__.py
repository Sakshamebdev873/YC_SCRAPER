"""Domain registry for send_emails.py.

Each domain module owns its own pitch content (bio/system prompt/subject/
follow-ups) and knows how to load its own list of target rows. send_emails.py
stays domain-agnostic: it just asks the selected domain for rows and prompts.
"""

from . import job_application
from . import sales_pitch

DOMAINS = {
    "job": job_application,
    "sales": sales_pitch,
}


def get_domain(name: str):
    try:
        return DOMAINS[name]
    except KeyError:
        raise ValueError(f"Unknown domain '{name}'. Choices: {', '.join(DOMAINS)}")
