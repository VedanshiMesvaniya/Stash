"""
email_service.py
Sends transactional email (currently just registration verification codes)
via SMTP - configured by default for Gmail, but works with any standard
SMTP server. Uses Python's built-in smtplib, so no extra dependency.

Configure via env vars (see .env.example):
  SMTP_HOST       defaults to smtp.gmail.com
  SMTP_PORT       defaults to 587 (STARTTLS)
  SMTP_USERNAME   your full Gmail address, e.g. noreplystash2026@gmail.com
  SMTP_PASSWORD   a Google *App Password* (NOT your normal Gmail password -
                  requires 2-Step Verification; generate one at
                  https://myaccount.google.com/apppasswords)
  SMTP_FROM_EMAIL defaults to SMTP_USERNAME
  SMTP_FROM_NAME  display name shown to recipients, defaults to "Stash"

Gmail is fine for a small app's verification codes, but it's not built
for high-volume transactional mail - if Stash ever needs to send at real
scale, a dedicated provider (Brevo, SES, Postmark, etc.) would be a
better fit than a personal/service Gmail account.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip() or "587")
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "").strip() or SMTP_USERNAME
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Stash").strip() or "Stash"

# Harvest Moon palette, matching frontend/src/styles.css, so the email
# looks like it came from the app rather than a generic mailer template.
_ACCENT = "#ffb4a4"
_ACCENT_2 = "#ffb688"
_BG = "#151313"


class EmailSendError(Exception):
    """Raised when the SMTP send fails for any reason."""


def _verification_email_html(code: str) -> str:
    return f"""
    <html>
      <body style="margin:0; padding:32px 16px; background-color:{_BG}; font-family:'Hanken Grotesk', Arial, sans-serif;">
        <div style="max-width:420px; margin:0 auto; background-color:#1d1a1a; border-radius:20px; padding:32px; text-align:center;">
          <div style="font-size:15px; letter-spacing:0.08em; text-transform:uppercase; color:{_ACCENT_2}; font-family:'JetBrains Mono', monospace;">Stash</div>
          <h1 style="color:#f5efe9; font-size:22px; margin:16px 0 8px;">Verify your email</h1>
          <p style="color:#b8afa8; font-size:14px; line-height:1.5; margin:0 0 24px;">
            Use the code below to finish creating your Stash account. It expires in 10 minutes.
          </p>
          <div style="display:inline-block; padding:16px 28px; border-radius:14px; background:linear-gradient(135deg, {_ACCENT}, {_ACCENT_2}); color:#151313; font-size:32px; font-weight:700; letter-spacing:0.3em; font-family:'JetBrains Mono', monospace;">
            {code}
          </div>
          <p style="color:#6f665f; font-size:12px; margin:24px 0 0;">
            If you didn't try to sign up for Stash, you can safely ignore this email.
          </p>
        </div>
      </body>
    </html>
    """


def send_verification_email(to_email: str, code: str) -> None:
    """Sends the 6-digit verification code to to_email. Raises
    EmailSendError on any failure - callers should catch this and surface
    a clean error rather than letting the raw exception leak upward."""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise EmailSendError(
            "Email sending isn't configured. Set SMTP_USERNAME and SMTP_PASSWORD "
            "(an app password, not your regular account password)."
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = f"{code} is your Stash verification code"
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message.attach(MIMEText(_verification_email_html(code), "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, [to_email], message.as_string())
    except smtplib.SMTPAuthenticationError as e:
        raise EmailSendError(
            "SMTP login failed - check SMTP_USERNAME/SMTP_PASSWORD. If using Gmail, "
            "SMTP_PASSWORD must be an App Password, not your normal password."
        ) from e
    except smtplib.SMTPException as e:
        raise EmailSendError(f"Could not send email: {e}") from e
    except OSError as e:
        raise EmailSendError(f"Could not reach SMTP server {SMTP_HOST}:{SMTP_PORT}: {e}") from e
