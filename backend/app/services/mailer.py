"""Plain SMTP delivery. Messages are sent only when the server has mail settings."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import Settings


def smtp_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host.strip() and settings.smtp_from.strip())


def send_email(settings: Settings, *, recipient: str, subject: str, body: str) -> None:
    if not smtp_configured(settings):
        raise RuntimeError("email_not_configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as client:
        if settings.smtp_port != 25:
            client.starttls()
        if settings.smtp_username.strip():
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
