"""
api/settings.py
Settings read/update (now just fields on the User row), backup/restore, and
offline-sync reconciliation. All scoped per logged-in user.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.database import get_db
from app.database import models
from app.auth.auth import get_current_user
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
    for field, value in payload.dict(exclude_unset=True).items():
        if field == "lock_pin":
            continue
        if field == "theme":
            value = _normalize_theme(value)
        if field == "currency":
            value = _normalize_currency(value)
        setattr(user, field, value)
    if payload.lock_pin is not None:
        from app.auth.password import hash_password

        user.lock_pin_hash = hash_password(payload.lock_pin) if payload.lock_pin else None
    db.commit()
    return {"ok": True}


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
