"""
api/auth.py
Login, logout, and JSON session helpers for the React app. There is
deliberately NO first-run/setup flow anymore - accounts are pre-created via
seed.py (see that file), and login is by username + password, not a single
shared app password.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.auth import auth as auth_logic
from app.auth.password import verify_password, hash_password
from app.auth.session import login_session, logout_session, is_authenticated, current_user_id
from app.database import crud

router = APIRouter()


def _normalize_theme(theme: str | None) -> str:
    if not theme:
        return "obsidian"
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
            "theme": _normalize_theme(user.theme if user else "obsidian"),
            "currency": user.currency if user else "INR",
            "lock_enabled": user.lock_enabled if user else False,
            "biometric_enabled": user.biometric_enabled if user else False,
            "has_lock_pin": bool(user.lock_pin_hash) if user else False,
            "monthly_alert_amount": user.monthly_alert_amount if user else None,
            "salary_day": user.salary_day if user else None,
        } if user else None,
    }


@router.post("/api/auth/login")
def api_login(payload: LoginPayload, request: Request, db: Session = Depends(get_db)):
    user = auth_logic.attempt_login(db, payload.username, payload.password)
    if user:
        login_session(request, user.id, user.username)
        return {"ok": True}
    return {"ok": False, "error": "Incorrect username or password"}


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
    if verify_password(payload.pin, user.lock_pin_hash):
        return {"ok": True}
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
