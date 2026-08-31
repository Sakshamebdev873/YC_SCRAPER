"""Gmail SMTP. The only module that imports smtplib."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

APP_PASSWORD_HELP = (
    "Gmail requires an App Password (not your regular password).\n"
    "Create one at: https://myaccount.google.com/apppasswords\n"
    "  1. Enable 2FA first if not already on\n"
    "  2. Create App Password -> select 'Mail' -> copy the 16-char code\n"
    "  3. Put that code in .env as GMAIL_PASSWORD"
)


def gmail_credentials() -> tuple:
    email = os.environ.get("GMAIL_EMAIL", "").strip()
    password = os.environ.get("GMAIL_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError(
            "GMAIL_EMAIL and GMAIL_PASSWORD must be set in .env.\n" + APP_PASSWORD_HELP
        )
    return email, password


def connect_smtp(email: str, password: str) -> smtplib.SMTP:
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(email, password)
    return smtp


def send_email(smtp, from_addr: str, to_addr: str, subject: str, body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))
    smtp.sendmail(from_addr, to_addr, msg.as_string())
