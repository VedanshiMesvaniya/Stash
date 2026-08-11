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

from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.database import crud
from app.database.database import get_db
from app.database import models
from .password import verify_password
from .session import is_authenticated, current_user_id


def attempt_login(db: Session, username: str, password: str) -> models.User | None:
    user = crud.get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


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
