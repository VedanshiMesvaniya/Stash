"""
auth.py
Login for Stash. As of the move to open signup, accounts are created via
/api/auth/signup (email + password) or /api/auth/google (Google sign-in) -
see app/api/auth.py. attempt_login looks up by email first since that's
now the identifier used at the login form; it falls back to username so
any pre-existing (pre-open-signup) accounts without an email set still work.
"""

from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.database import crud
from app.database.database import get_db
from app.database import models
from .password import verify_password
from .session import is_authenticated, current_user_id


def attempt_login(db: Session, identifier: str, password: str) -> models.User | None:
    user = crud.get_user_by_email(db, identifier) or crud.get_user_by_username(db, identifier)
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
