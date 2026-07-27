"""
mailer.py
Sends transactional email (currently: signup verification codes) via SMTP.

Uses stdlib smtplib rather than a third-party email API, so no new
dependency is needed - works with Gmail SMTP (with an App Password, not
your normal password), or any SMTP relay (Resend, SendGrid, Postmark, etc.
all offer one). Configure via env vars - see .env.example / DEPLOY.md.

If SMTP isn't configured, send_verification_code() logs the code to the
server console instead of raising, so local development still works
without setting up real email delivery.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("stash.mailer")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME).strip()


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM)


def send_email(to: str, subject: str, body: str) -> bool:
    """Returns True if actually sent over SMTP, False if it fell back to
    console logging (SMTP not configured) - callers use this to decide
    whether to tell the user 'check your email' vs surface a setup issue."""
    if not is_configured():
        logger.warning(
            "SMTP not configured (set SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD/SMTP_FROM) - "
            "printing email instead of sending.\nTo: %s\nSubject: %s\n%s",
            to, subject, body,
        )
        return False

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)
    return True


def send_verification_code(to: str, code: str) -> bool:
    subject = "Your Stash verification code"
    body = (
        f"Your Stash verification code is: {code}\n\n"
        "This code expires in 10 minutes. If you didn't request this, you can ignore this email."
    )
    return send_email(to, subject, body)
