import pytest

from app.services.mailer import gmail_credentials, send_email


class FakeSMTP:
    def __init__(self):
        self.sent = []

    def sendmail(self, from_addr, to_addr, message):
        self.sent.append((from_addr, to_addr, message))


def test_send_email_builds_a_message():
    smtp = FakeSMTP()
    send_email(smtp, "me@gmail.com", "you@acme.com", "Hi there", "Body line\nSecond line")
    from_addr, to_addr, message = smtp.sent[0]
    assert from_addr == "me@gmail.com"
    assert to_addr == "you@acme.com"
    assert "Subject: Hi there" in message
    assert "To: you@acme.com" in message


def test_send_email_handles_non_ascii():
    smtp = FakeSMTP()
    send_email(smtp, "me@gmail.com", "you@acme.com", "Café", "Body — with an em dash")
    assert smtp.sent


def test_gmail_credentials_reads_env(monkeypatch):
    monkeypatch.setenv("GMAIL_EMAIL", "me@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "abcd efgh ijkl mnop")
    assert gmail_credentials() == ("me@gmail.com", "abcd efgh ijkl mnop")


def test_gmail_credentials_missing_raises(monkeypatch):
    monkeypatch.setenv("GMAIL_EMAIL", "")
    monkeypatch.setenv("GMAIL_PASSWORD", "")
    with pytest.raises(RuntimeError) as excinfo:
        gmail_credentials()
    assert "App Password" in str(excinfo.value)
