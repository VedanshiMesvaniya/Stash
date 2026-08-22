"""
email_service.py
Sends transactional email (currently just registration verification codes)
via Brevo's REST API (https://api.brevo.com/v3/smtp/email). Uses httpx
directly instead of the brevo-python SDK - it's one HTTP POST, and this
avoids pulling in a heavy extra dependency for something this small.

Configure via env vars (see .env.example):
  BREVO_API_KEY      required to actually send mail
  BREVO_SENDER_EMAIL sender address (must be a verified sender in Brevo)
  BREVO_SENDER_NAME  display name for the sender, defaults to "Stash"
"""

import os

import httpx

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "").strip()
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Stash").strip() or "Stash"

# Harvest Moon palette, matching frontend/src/styles.css, so the email
# looks like it came from the app rather than a generic mailer template.
_ACCENT = "#ffb4a4"
_ACCENT_2 = "#ffb688"
_BG = "#151313"


class EmailSendError(Exception):
    """Raised when Brevo rejects the send or the request itself fails."""


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
    if not BREVO_API_KEY or not BREVO_SENDER_EMAIL:
        raise EmailSendError(
            "Email sending isn't configured. Set BREVO_API_KEY and BREVO_SENDER_EMAIL."
        )

    body = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": f"{code} is your Stash verification code",
        "htmlContent": _verification_email_html(code),
    }
    headers = {
        "api-key": BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }

    try:
        response = httpx.post(BREVO_API_URL, json=body, headers=headers, timeout=10.0)
    except httpx.HTTPError as e:
        raise EmailSendError(f"Could not reach Brevo: {e}") from e

    if response.status_code >= 300:
        raise EmailSendError(f"Brevo rejected the email (status {response.status_code}): {response.text}")
