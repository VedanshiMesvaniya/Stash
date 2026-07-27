"""
api/auth.py
Login, logout, signup, Google sign-in, and JSON session helpers for the
React app. Open signup: anyone can create an account with an email +
password, or via Google sign-in (which auto-creates an account on first
login if the email isn't already registered). See app/auth/auth.py for
the reasoning on why login now looks up by email.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.auth import auth as auth_logic
from app.auth.password import verify_password, hash_password
from app.auth.session import login_session, logout_session, is_authenticated, current_user_id
from app.database import crud
from app.services import currency as currency_service
from app.services import mailer

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
VERIFICATION_CODE_TTL_MINUTES = 10
VERIFICATION_MAX_ATTEMPTS = 5


def _normalize_theme(theme: str | None) -> str:
    if not theme:
        return "mist"
    if theme == "dark":
        return "obsidian"
    if theme == "light":
        return "mist"
    return theme


class LoginPayload(BaseModel):
    email: str
    password: str


class RequestCodePayload(BaseModel):
    email: str


class VerifyCodePayload(BaseModel):
    email: str
    code: str
    password: str
    display_name: str | None = None


class GoogleAuthPayload(BaseModel):
    credential: str  # Google Identity Services ID token (JWT)


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
        "email": user.email if user else None,
        "email_verified": user.email_verified if user else None,
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
    user = auth_logic.attempt_login(db, payload.email, payload.password)
    if user:
        login_session(request, user.id, user.username)
        return {"ok": True}
    return {"ok": False, "error": "Incorrect email or password"}


@router.post("/api/auth/signup/request-code")
def api_signup_request_code(payload: RequestCodePayload, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return {"ok": False, "error": "Enter a valid email address"}
    if crud.get_user_by_email(db, email) or crud.get_user_by_username(db, email):
        return {"ok": False, "error": "An account with that email already exists"}

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES)
    crud.create_email_verification(db, email, hash_password(code), expires_at, purpose="signup")
    sent = mailer.send_verification_code(email, code)
    return {
        "ok": True,
        # In local dev without SMTP configured, the code is logged to the
        # server console instead of emailed - tell the frontend so it can
        # show a helpful hint instead of implying an email was sent.
        "delivered": sent,
    }


@router.post("/api/auth/signup/verify-code")
def api_signup_verify_code(payload: VerifyCodePayload, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if len(payload.password) < 8:
        return {"ok": False, "error": "Password must be at least 8 characters"}

    verification = crud.get_email_verification(db, email, purpose="signup")
    if not verification:
        return {"ok": False, "error": "Request a new code - none found for this email"}
    if verification.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        crud.delete_email_verification(db, verification)
        return {"ok": False, "error": "That code expired - request a new one"}
    if verification.attempts >= VERIFICATION_MAX_ATTEMPTS:
        crud.delete_email_verification(db, verification)
        return {"ok": False, "error": "Too many incorrect attempts - request a new code"}
    if not verify_password(payload.code.strip(), verification.code_hash):
        crud.increment_verification_attempts(db, verification)
        return {"ok": False, "error": "Incorrect code"}

    # Re-check for a race where the email got registered between requesting
    # the code and verifying it (e.g. two signup attempts at once).
    if crud.get_user_by_email(db, email) or crud.get_user_by_username(db, email):
        crud.delete_email_verification(db, verification)
        return {"ok": False, "error": "An account with that email already exists"}

    user = crud.create_user(
        db, email, hash_password(payload.password), display_name=payload.display_name, email_verified=True,
    )
    crud.delete_email_verification(db, verification)
    login_session(request, user.id, user.username)
    return {"ok": True}


@router.post("/api/auth/google")
def api_google_auth(payload: GoogleAuthPayload, request: Request, db: Session = Depends(get_db)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in isn't configured on this server (missing GOOGLE_CLIENT_ID).",
        )
    # Verifying the ID token via Google's tokeninfo endpoint (rather than
    # checking the JWT signature locally) keeps this dependency-free - no
    # google-auth library needed, just an HTTPS call Google explicitly
    # supports for this purpose. Fine at Stash's traffic level; a
    # higher-traffic app should verify signatures locally against Google's
    # published JWKs instead of round-tripping to Google per login.
    try:
        resp = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": payload.credential},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not reach Google to verify sign-in")
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google sign-in token")

    claims = resp.json()
    if claims.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google token was not issued for this app")
    if claims.get("email_verified") not in ("true", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google account email isn't verified")

    google_sub = claims.get("sub")
    email = (claims.get("email") or "").strip().lower()
    name = claims.get("name")

    user = crud.get_user_by_google_sub(db, google_sub)
    if not user:
        user = crud.get_user_by_email(db, email)
        if user:
            user.google_sub = google_sub  # link Google to the existing email/password account
            db.commit()
    if not user:
        # First-time sign-in for this email: open signup creates the account.
        # A random, never-shared password hash fills the NOT NULL column;
        # this account can only be reached via Google sign-in unless the
        # person later sets a password from Settings.
        user = crud.create_user(
            db, email, hash_password(secrets.token_urlsafe(32)), display_name=name, google_sub=google_sub,
            email_verified=True,
        )
    login_session(request, user.id, user.username)
    return {"ok": True}


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
