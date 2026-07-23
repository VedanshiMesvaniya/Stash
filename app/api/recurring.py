"""
api/recurring.py
Recurring schedule CRUD and auto-post sync, scoped per user.
"""

from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database import models
from app.auth.auth import get_current_user
from app.services import recurring as recurring_service

router = APIRouter()


class RecurringCreate(BaseModel):
    name: str
    category_or_source: str
    transaction_type: str
    amount: float
    description: str | None = None
    start_date: date
    interval_months: int = 1
    total_cycles: int | None = None
    auto_post: bool | None = None


class RecurringUpdate(BaseModel):
    name: str | None = None
    category_or_source: str | None = None
    transaction_type: str | None = None
    amount: float | None = None
    description: str | None = None
    start_date: date | None = None
    interval_months: int | None = None
    total_cycles: int | None = None
    active: bool | None = None
    auto_post: bool | None = None


class RecurringConfirmPost(BaseModel):
    amount: float | None = None
    post_date: date | None = None


@router.get("/recurring")
def list_recurring(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return recurring_service.list_recurring(db, user.id)


@router.post("/recurring")
def create_recurring(payload: RecurringCreate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return recurring_service.create_recurring(db, user.id, **payload.model_dump())


@router.put("/recurring/{recurring_id}")
def update_recurring(recurring_id: int, payload: RecurringUpdate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return recurring_service.update_recurring(db, user.id, recurring_id, **payload.model_dump(exclude_unset=True))


@router.post("/recurring/{recurring_id}/disable")
def disable_recurring(recurring_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return recurring_service.disable_recurring(db, user.id, recurring_id)


@router.post("/recurring/sync")
def sync_recurring(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return recurring_service.sync_due_recurring(db, user.id)


@router.get("/recurring/due")
def due_recurring(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Salary/Rent (or any manual auto_post=False) schedules that are due
    and waiting for the user to confirm via the dashboard '+' button."""
    return recurring_service.list_due_manual(db, user.id)


@router.post("/recurring/{recurring_id}/confirm")
def confirm_recurring_post(
    recurring_id: int,
    payload: RecurringConfirmPost,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    result = recurring_service.confirm_manual_post(db, user.id, recurring_id, amount=payload.amount, post_date=payload.post_date)
    if not result:
        return {"ok": False, "error": "Schedule not found"}
    return {"ok": True, **result}
