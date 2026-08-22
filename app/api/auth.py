"""
api/auth.py
Login, logout, and JSON session helpers for the React app. There is
deliberately NO first-run/setup flow anymore - accounts are pre-created via
seed.py (see that file), and login is by username + password, not a single
shared app password.
"""

import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.auth import auth as auth_logic
from app.auth.password import verify_password, hash_password
from app.auth.session import login_session, logout_session, is_authenticated, current_user_id
from app.database import crud
from app.services import currency as currency_service

# Same brute-force protection as login (see auth/auth.py), applied to the
# app-lock PIN independently since it's a much shorter secret and has its
# own attempt counter on the User row.
PIN_MAX_ATTEMPTS = 5
PIN_LOCKOUT_SECONDS = 15 * 60

router = APIRouter()


def _normalize_theme(theme: str | None) -> str:
    if not theme:
        return "mist"
    if theme == "dark":
        return "obsidian"
    if theme == "light":
        return "mist"
    return theme


class LoginPayload(BaseModel):
    username: str
    password: str


class UnlockPayload(BaseModel):
    pin: str


class LockSettingsPayload(BaseModel):
    lock_enabled: bool = False
    biometric_enabled: bool = False
    pin: str | None = None


@router.get("/api/auth/session")
def session_state(request: Request, db: Session = Depends(get_db)):
    authenticated = is_authenticated(request)
    user = None
    if authenticated:
        user = crud.get_user(db, current_user_id(request))
    return {
        "authenticated": bool(user),
        "first_run": False,
        "username": user.username if user else None,
        "display_name": user.display_name if user else None,
        "settings": {
            "theme": _normalize_theme(user.theme if user else "mist"),
            "currency": user.currency if user else "INR",
            "lock_enabled": user.lock_enabled if user else False,
            "biometric_enabled": user.biometric_enabled if user else False,
            "has_lock_pin": bool(user.lock_pin_hash) if user else False,
            "monthly_alert_amount": (
                currency_service.convert_amount(user.monthly_alert_amount, "INR", user.currency)
                if user and user.monthly_alert_amount is not None
                else None
            ),
            "salary_day": user.salary_day if user else None,
        } if user else None,
    }


@router.post("/api/auth/login")
def api_login(payload: LoginPayload, request: Request, db: Session = Depends(get_db)):
    user, lockout_message = auth_logic.attempt_login(db, payload.username, payload.password)
    if user:
        login_session(request, user.id, user.username)
        return {"ok": True}
    return {"ok": False, "error": lockout_message or "Incorrect username or password"}


@router.post("/api/auth/logout")
def api_logout(request: Request, db: Session = Depends(get_db)):
    user = crud.get_user(db, current_user_id(request)) if is_authenticated(request) else None
    if user and (user.username or "").lower() == "guest":
        crud.purge_user_data(db, user.id)
    logout_session(request)
    return {"ok": True}


@router.post("/api/auth/unlock")
def api_unlock(payload: UnlockPayload, request: Request, db: Session = Depends(get_db)):
    auth_logic.require_auth(request)
    user = crud.get_user(db, current_user_id(request))
    if not user or not user.lock_pin_hash:
        return {"ok": False, "error": "No app lock configured"}

    now = time.time()
    if user.pin_locked_until and now < user.pin_locked_until:
        minutes = max(1, int((user.pin_locked_until - now) // 60) + 1)
        return {"ok": False, "error": f"Too many failed attempts. Try again in {minutes} minute(s)."}

    if verify_password(payload.pin, user.lock_pin_hash):
        user.failed_pin_attempts = 0
        user.pin_locked_until = None
        db.commit()
        return {"ok": True}

    user.failed_pin_attempts = (user.failed_pin_attempts or 0) + 1
    if user.failed_pin_attempts >= PIN_MAX_ATTEMPTS:
        user.pin_locked_until = now + PIN_LOCKOUT_SECONDS
    db.commit()
    return {"ok": False, "error": "Incorrect PIN"}


@router.post("/api/auth/lock-settings")
def api_lock_settings(payload: LockSettingsPayload, request: Request, db: Session = Depends(get_db)):
    auth_logic.require_auth(request)
    user = crud.get_user(db, current_user_id(request))
    if not user:
        return {"ok": False, "error": "Not authenticated"}
    user.lock_enabled = payload.lock_enabled
    user.biometric_enabled = payload.biometric_enabled
    if payload.pin is not None:
        user.lock_pin_hash = hash_password(payload.pin) if payload.pin else None
    db.commit()
    return {"ok": True}
