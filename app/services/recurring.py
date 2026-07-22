"""
recurring.py
Recurring schedule management and idempotent auto-posting, scoped per user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import calendar

from sqlalchemy.orm import Session

from app.database import models, crud
from app.services import currency as currency_service


@dataclass
class RecurringProgress:
    progress_percent: float
    cycle_progress_percent: float
    completed_cycles: int
    total_cycles: int | None
    active: bool
    next_due_date: date


def has_active_schedule_for(db: Session, user_id: int, transaction_type: str, category_or_source: str) -> bool:
    """Used by the recurring-detection nudge (feature #23) to avoid
    suggesting a schedule the user already has set up."""
    return db.query(models.RecurringTransaction).filter(
        models.RecurringTransaction.user_id == user_id,
        models.RecurringTransaction.transaction_type == transaction_type,
        models.RecurringTransaction.category_or_source == category_or_source,
        models.RecurringTransaction.active.is_(True),
    ).first() is not None


def _add_months(source_date: date, months: int) -> date:
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _current_cycle_progress(row: models.RecurringTransaction, today: date | None = None) -> float:
    today = today or date.today()
    if today >= row.next_due_date:
        return 100.0
    previous_due = _add_months(row.next_due_date, -row.interval_months)
    total_days = max((row.next_due_date - previous_due).days, 1)
    elapsed_days = max((today - previous_due).days, 0)
    return min(100.0, (elapsed_days / total_days) * 100.0)


def _completion_percent(row: models.RecurringTransaction) -> float:
    if not row.total_cycles:
        return 0.0
    return min(100.0, (row.cycles_completed / row.total_cycles) * 100.0)


def _serialize_schedule(row: models.RecurringTransaction, currency: str | None = None) -> dict:
    current_progress = _current_cycle_progress(row)
    completion = _completion_percent(row)
    progress_percent = completion if row.total_cycles else current_progress
    status = "active" if row.active else "disabled"
    if row.total_cycles and row.cycles_completed >= row.total_cycles:
        status = "completed"
    active_currency = currency or "INR"
    return {
        "id": row.id,
        "name": row.name,
        "category_or_source": row.category_or_source,
        "transaction_type": row.transaction_type,
        "amount": currency_service.convert_amount(row.amount, "INR", active_currency),
        "description": row.description,
        "cadence": row.cadence,
        "start_date": str(row.start_date),
        "next_due_date": str(row.next_due_date),
        "interval_months": row.interval_months,
        "total_cycles": row.total_cycles,
        "cycles_completed": row.cycles_completed,
        "active": bool(row.active),
        "completion_percent": round(completion, 2) if row.total_cycles else None,
        "cycle_progress_percent": round(current_progress, 2),
        "progress_percent": round(progress_percent, 2),
        "status": status,
    }


def list_recurring(db: Session, user_id: int) -> list[dict]:
    user = crud.get_user(db, user_id)
    currency = user.currency if user else "INR"
    rows = db.query(models.RecurringTransaction).filter(
        models.RecurringTransaction.user_id == user_id
    ).order_by(models.RecurringTransaction.created_at.desc()).all()
    return [_serialize_schedule(row, currency) for row in rows]


def create_recurring(
    db: Session,
    user_id: int,
    *,
    name: str,
    category_or_source: str,
    transaction_type: str,
    amount: float,
    description: str | None,
    start_date: date,
    interval_months: int = 1,
    total_cycles: int | None = None,
):
    user = crud.get_user(db, user_id)
    currency = user.currency if user else "INR"
    row = models.RecurringTransaction(
        user_id=user_id,
        name=name,
        category_or_source=category_or_source,
        transaction_type=transaction_type,
        amount=currency_service.convert_amount(amount, currency, "INR"),
        description=description,
        cadence="monthly" if interval_months == 1 else "custom",
        start_date=start_date,
        next_due_date=start_date,
        interval_months=interval_months,
        total_cycles=total_cycles,
        cycles_completed=0,
        active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_schedule(row, currency)


def _get_owned(db: Session, user_id: int, recurring_id: int):
    return db.query(models.RecurringTransaction).filter(
        models.RecurringTransaction.id == recurring_id,
        models.RecurringTransaction.user_id == user_id,
    ).first()


def update_recurring(db: Session, user_id: int, recurring_id: int, **fields):
    user = crud.get_user(db, user_id)
    currency = user.currency if user else "INR"
    row = _get_owned(db, user_id, recurring_id)
    if not row:
        return None
    for key, value in fields.items():
        if value is None:
            continue
        if key == "amount":
            value = currency_service.convert_amount(value, currency, "INR")
        setattr(row, key, value)
    if "start_date" in fields and fields["start_date"]:
        row.next_due_date = fields["start_date"]
    db.commit()
    db.refresh(row)
    return _serialize_schedule(row, currency)


def disable_recurring(db: Session, user_id: int, recurring_id: int):
    row = _get_owned(db, user_id, recurring_id)
    if not row:
        return None
    row.active = False
    db.commit()
    db.refresh(row)
    return _serialize_schedule(row)


def _create_ledger_entry(db: Session, user_id: int, row: models.RecurringTransaction, due_date: date):
    desc = row.description or f"Recurring {row.name}"
    if row.transaction_type == "income":
        txn = crud.create_income(db, user_id, amount=row.amount, source=row.category_or_source, description=desc, txn_date=due_date)
    else:
        txn = crud.create_expense(db, user_id, amount=row.amount, category=row.category_or_source, description=desc, txn_date=due_date)
    posting = models.RecurringPosting(
        recurring_id=row.id,
        posted_for_date=due_date,
        transaction_type=row.transaction_type,
        transaction_id=txn.id,
        amount=row.amount,
    )
    db.add(posting)
    db.flush()
    db.refresh(posting)
    return txn, posting


def sync_due_recurring(db: Session, user_id: int, through_date: date | None = None) -> dict:
    today = through_date or date.today()
    schedules = db.query(models.RecurringTransaction).filter(
        models.RecurringTransaction.user_id == user_id,
        models.RecurringTransaction.active.is_(True),
    ).all()
    created = []
    skipped = 0

    for row in schedules:
        while row.active and row.next_due_date <= today:
            already_posted = (
                db.query(models.RecurringPosting)
                .filter(
                    models.RecurringPosting.recurring_id == row.id,
                    models.RecurringPosting.posted_for_date == row.next_due_date,
                )
                .first()
            )
            if already_posted:
                skipped += 1
                row.cycles_completed += 1
                if row.total_cycles and row.cycles_completed >= row.total_cycles:
                    row.active = False
                    break
                row.next_due_date = _add_months(row.next_due_date, row.interval_months)
                db.commit()
                continue

            txn, posting = _create_ledger_entry(db, user_id, row, row.next_due_date)
            row.cycles_completed += 1
            created.append(
                {
                    "recurring_id": row.id,
                    "posting_id": posting.id,
                    "transaction_id": txn.id,
                    "transaction_type": row.transaction_type,
                    "amount": row.amount,
                    "due_date": str(row.next_due_date),
                    "name": row.name,
                }
            )

            if row.total_cycles and row.cycles_completed >= row.total_cycles:
                row.active = False
                db.commit()
                break

            row.next_due_date = _add_months(row.next_due_date, row.interval_months)
            db.commit()

    return {"created": created, "skipped": skipped, "created_count": len(created)}
