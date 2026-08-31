import pytest

from app.services.personalize import (
    build_messages, generate_body, render_followup_body, render_subject,
)

TEMPLATES = {
    "system_prompt": "You write emails.",
    "user_prompt": (
        "Write the email for {company_name} (YC {batch}).\n"
        "Founder: {founder_first_name}\nAbout: {company_description}\n"
        "Website: {company_website}"
    ),
    "subject": "Question about the SDE Intern role at {company_name}",
    "followup_subject": "Re: SDE Intern @ {company_name}",
    "followup_1": "Following up about {company_name}.",
    "followup_2": "Second nudge about {company_name}.",
    "followup_3": "Last note about {company_name}.",
}

CONTACT = {
    "company_name": "Acme",
    "batch": "Winter 2026",
    "founder_name": "Ada Lovelace",
    "company_description": "robots for warehouses",
    "company_website": "https://acme.com",
}


class FakeCompletions:
    def __init__(self, reply="Hi Ada,\n\nBody.\n"):
        self.reply = reply
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class Msg:
            content = self.reply

        class Choice:
            message = Msg()

        class Resp:
            choices = [Choice()]

        return Resp()


class FakeClient:
    def __init__(self, reply="Hi Ada,\n\nBody.\n"):
        self.chat = type("Chat", (), {"completions": FakeCompletions(reply)})()


def test_build_messages_uses_first_name_and_fields():
    system, user = build_messages(TEMPLATES, CONTACT)
    assert system == {"role": "system", "content": "You write emails."}
    assert "Acme" in user["content"]
    assert "Founder: Ada" in user["content"]
    assert "robots for warehouses" in user["content"]


def test_build_messages_blank_name_falls_back():
    contact = {**CONTACT, "founder_name": ""}
    _, user = build_messages(TEMPLATES, contact)
    assert "Founder: there" in user["content"]


def test_build_messages_blank_description_falls_back():
    contact = {**CONTACT, "company_description": "   "}
    _, user = build_messages(TEMPLATES, contact)
    assert "an early-stage startup" in user["content"]


def test_generate_body_calls_openai_and_strips():
    client = FakeClient(reply="  Hi Ada,\n\nBody.  ")
    body = generate_body(client, TEMPLATES, CONTACT)
    assert body == "Hi Ada,\n\nBody."
    call = client.chat.completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["temperature"] == 0.3
    assert call["max_tokens"] == 400
    assert len(call["messages"]) == 2


def test_render_subject_initial_and_followup():
    assert render_subject(TEMPLATES, CONTACT, 0) == \
        "Question about the SDE Intern role at Acme"
    assert render_subject(TEMPLATES, CONTACT, 2) == "Re: SDE Intern @ Acme"


def test_render_followup_body():
    assert render_followup_body(TEMPLATES, CONTACT, 2) == "Second nudge about Acme."


def test_render_followup_body_rejects_round_zero():
    with pytest.raises(ValueError):
        render_followup_body(TEMPLATES, CONTACT, 0)
