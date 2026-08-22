"""
registration.py
Self-service sign-up: email -> 6-digit code -> verified account. Nothing
lands in the `users` table until the code is confirmed (see
models.PendingRegistration). Two steps:

  1. start_registration()  - validate + stash a pending row + email the code
  2. complete_registration() - check the code, promote pending -> real User

Both are called from api/auth.py's /register/send-code and
/register/verify-code endpoints.
"""

import random
import re
import time

from sqlalchemy.orm import Session

from app.database import crud, models
from app.auth.password import hash_password, verify_password
from app.services import email_service

CODE_TTL_SECONDS = 10 * 60
RESEND_COOLDOWN_SECONDS = 60
MAX_CODE_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 8

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def _validate_new_account_fields(db: Session, email: str, username: str, password: str) -> str | None:
    """Returns an error message, or None if everything checks out."""
    email = email.strip().lower()
    username = username.strip()

    if not _EMAIL_RE.match(email):
        return "Enter a valid email address."
    if not username:
        return "Username is required."
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if crud.get_user_by_email(db, email):
        return "An account with this email already exists."
    if crud.get_user_by_username(db, username):
        return "That username is already taken."
    other_pending = db.query(models.PendingRegistration).filter(
        models.PendingRegistration.username.ilike(username),
        models.PendingRegistration.email != email,
    ).first()
    if other_pending:
        return "That username is already taken."
    return None


def start_registration(db: Session, email: str, username: str, password: str) -> tuple[bool, str | None]:
    """Validates the signup, creates/refreshes the pending row, and emails
    the code. Returns (ok, error) - on success error is None."""
    email = email.strip().lower()
    username = username.strip()

    error = _validate_new_account_fields(db, email, username, password)
    if error:
        return False, error

    now = time.time()
    pending = db.query(models.PendingRegistration).filter(
        models.PendingRegistration.email == email
    ).first()

    if pending and now - pending.last_sent_at < RESEND_COOLDOWN_SECONDS:
        wait = int(RESEND_COOLDOWN_SECONDS - (now - pending.last_sent_at))
        return False, f"Please wait {wait} second(s) before requesting another code."

    code = _generate_code()

    try:
        email_service.send_verification_email(email, code)
    except email_service.EmailSendError as e:
        return False, str(e)

    if pending:
        pending.username = username
        pending.password_hash = hash_password(password)
        pending.code_hash = hash_password(code)
        pending.expires_at = now + CODE_TTL_SECONDS
        pending.failed_attempts = 0
        pending.last_sent_at = now
    else:
        pending = models.PendingRegistration(
            email=email,
            username=username,
            password_hash=hash_password(password),
            code_hash=hash_password(code),
            expires_at=now + CODE_TTL_SECONDS,
            failed_attempts=0,
            last_sent_at=now,
        )
        db.add(pending)
    db.commit()
    return True, None


def complete_registration(db: Session, email: str, code: str) -> tuple["models.User | None", str | None]:
    """Checks the code and, if it matches, promotes the pending row into a
    real User. Returns (user, error) - on success error is None."""
    email = email.strip().lower()
    now = time.time()

    pending = db.query(models.PendingRegistration).filter(
        models.PendingRegistration.email == email
    ).first()
    if not pending:
        return None, "No pending registration for this email. Start over."

    if now > pending.expires_at:
        db.delete(pending)
        db.commit()
        return None, "That code has expired. Request a new one."

    if not verify_password(code, pending.code_hash):
        pending.failed_attempts = (pending.failed_attempts or 0) + 1
        if pending.failed_attempts >= MAX_CODE_ATTEMPTS:
            db.delete(pending)
            db.commit()
            return None, "Too many incorrect attempts. Request a new code."
        db.commit()
        return None, "Incorrect code."

    # Re-check uniqueness in case another registration (or a seeded account)
    # grabbed the email/username while this one was pending verification.
    if crud.get_user_by_email(db, pending.email) or crud.get_user_by_username(db, pending.username):
        db.delete(pending)
        db.commit()
        return None, "That email or username was just taken. Please register again."

    user = models.User(
        username=pending.username,
        email=pending.email,
        password_hash=pending.password_hash,
        display_name=pending.username,
        currency="INR",
        theme="mist",
        monthly_alert_amount=1000.0,
        salary_day=1,
    )
    db.add(user)
    db.delete(pending)
    db.commit()
    db.refresh(user)
    return user, None
