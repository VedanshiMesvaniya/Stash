"""
api/settings.py
Settings read/update (now just fields on the User row), backup/restore, and
offline-sync reconciliation. All scoped per logged-in user.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.database import get_db
from app.database import models, crud
from app.database.seed import update_family_account_password
from app.auth.auth import get_current_user
from app.auth.password import hash_password, verify_password
from app.services import backup as backup_service
from app.services import sync as sync_service

# (Session import above is used by the type hints in update_settings/sync_offline_queue)

router = APIRouter()


def _normalize_theme(theme: str | None) -> str:
    if not theme:
        return "obsidian"
    if theme == "dark":
        return "obsidian"
    if theme == "light":
        return "mist"
    return theme


def _normalize_currency(currency: str | None) -> str:
    if not currency:
        return "INR"
    value = currency.strip().upper()
    aliases = {
        "UK": "GBP",
        "JAPAN": "JPY",
        "CHINA": "CNY",
        "KOREA": "KRW",
    }
    return aliases.get(value, value)


class SettingsUpdate(BaseModel):
    monthly_alert_amount: float | None = None
    salary_day: int | None = None
    currency: str | None = None
    theme: str | None = None
    username: str | None = None
    old_password: str | None = None
    new_password: str | None = None
    lock_enabled: bool | None = None
    biometric_enabled: bool | None = None
    lock_pin: str | None = None


class SyncPayload(BaseModel):
    transactions: list[dict]


@router.get("/settings")
def get_settings(request: Request, user: models.User = Depends(get_current_user)):
    return {
        "monthly_alert_amount": user.monthly_alert_amount,
        "salary_day": user.salary_day,
        "currency": _normalize_currency(user.currency),
        "theme": _normalize_theme(user.theme),
        "lock_enabled": user.lock_enabled,
        "biometric_enabled": user.biometric_enabled,
        "has_lock_pin": bool(user.lock_pin_hash),
    }


@router.put("/settings")
def update_settings(payload: SettingsUpdate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    data = payload.dict(exclude_unset=True)
    original_username = user.username

    username = data.pop("username", None)
    old_password = data.pop("old_password", None)
    new_password = data.pop("new_password", None)

    for field, value in data.items():
        if field == "lock_pin":
            continue
        if field == "theme":
            value = _normalize_theme(value)
        if field == "currency":
            value = _normalize_currency(value)
        setattr(user, field, value)

    if username is not None:
        next_username = username.strip()
        if not next_username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username cannot be empty")
        if next_username.lower() != user.username.lower():
            existing = crud.get_user_by_username(db, next_username)
            if existing and existing.id != user.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
            user.username = next_username
            request.session["username"] = next_username

    if new_password is not None:
        if not old_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is required to change password")
        if not verify_password(old_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect")
        if not new_password.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password cannot be empty")
        user.password_hash = hash_password(new_password)

    if payload.lock_pin is not None:
        user.lock_pin_hash = hash_password(payload.lock_pin) if payload.lock_pin else None
    db.commit()
    if new_password is not None:
        update_family_account_password(
            original_username,
            new_password,
            new_username=user.username if user.username != original_username else None,
        )
    return {"ok": True, "username": user.username}


@router.post("/backup")
def create_backup(request: Request, user: models.User = Depends(get_current_user)):
    path = backup_service.create_backup()
    return {"backup_file": path}


@router.get("/backup/list")
def list_backups(request: Request, user: models.User = Depends(get_current_user)):
    return backup_service.list_backups()


@router.post("/backup/restore")
def restore_backup(filename: str, request: Request, user: models.User = Depends(get_current_user)):
    backup_service.restore_backup(filename)
    return {"ok": True}


@router.post("/sync")
def sync_offline_queue(payload: SyncPayload, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    result = sync_service.reconcile_offline_queue(db, user.id, payload.transactions)
    return result
