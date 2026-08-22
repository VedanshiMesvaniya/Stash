"""
auth.py
Multi-user login for Stash. There is deliberately NO signup/setup flow and
NO recovery password backdoor - accounts are created ahead of time by you,
via seed.py, and handed out as username+password to each family member.
That was a specific requirement, not an oversight: fewer moving parts,
nobody can create an account they weren't given.

If a password needs resetting, do it with the CLI tool
(scripts/reset_password.py) which requires filesystem/shell access to the
server, not a network-facing password anyone could find in the repo.
"""

import time

from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.database import crud
from app.database.database import get_db
from app.database import models
from .password import verify_password
from .session import is_authenticated, current_user_id

# Brute-force protection: after this many wrong passwords in a row for an
# account, lock that account out (independent of who's guessing, or from
# where) for LOGIN_LOCKOUT_SECONDS. Bcrypt makes each guess slow, but that
# alone doesn't stop a patient scripted attack with no attempt limit at all.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


def attempt_login(db: Session, identifier: str, password: str) -> tuple[models.User | None, str | None]:
    """Returns (user, lockout_message). On success: (user, None). On a wrong
    password with attempts remaining, or on an unknown identifier: (None, None)
    - same generic "incorrect email/username or password" response either
    way, so this doesn't leak which accounts exist. `identifier` may be a
    username (legacy/seeded accounts) or an email (self-registered accounts
    always have one) - see crud.get_user_by_identifier. Once an account is
    locked out, returns (None, message) with a friendly wait-time regardless
    of whether the password given this time was actually correct, since
    accepting a correct password mid-lockout would defeat the point."""
    user = crud.get_user_by_identifier(db, identifier)
    if not user:
        return None, None

    now = time.time()
    if user.login_locked_until and now < user.login_locked_until:
        minutes = max(1, int((user.login_locked_until - now) // 60) + 1)
        return None, f"Too many failed attempts. Try again in {minutes} minute(s)."

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= LOGIN_MAX_ATTEMPTS:
            user.login_locked_until = now + LOGIN_LOCKOUT_SECONDS
        db.commit()
        return None, None

    user.failed_login_attempts = 0
    user.login_locked_until = None
    db.commit()
    return user, None


def require_auth(request: Request):
    """FastAPI dependency: raises 401 if not logged in (for JSON routes that
    only need to check auth, not load the user object)."""
    if not is_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    """FastAPI dependency: returns the logged-in User row, or raises 401.
    Use this (not require_auth) in any route that reads/writes user data -
    it's what every crud.* call below uses to scope queries to user_id."""
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
