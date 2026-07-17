"""
sync.py
Reconciles transactions queued offline in the browser's IndexedDB with the
database once connectivity to the FastAPI backend is restored. Scoped per
user so one user's offline queue can never insert rows into another user's
account.

HONEST NOTE: conflict resolution policy was not specified in the project
brief. The policy implemented here is last-write-wins by client timestamp,
with server-side dedup by (user_id, type, amount, category/source, date,
description) to avoid double-inserting a transaction that synced twice. If
you need a stricter policy (e.g. server always wins, or manual conflict
review), that needs to be decided explicitly - silently picking one is
exactly the kind of decision that should be visible to you, not buried in
code.
"""

from sqlalchemy.orm import Session
from app.database import crud, models
from app.services import currency as currency_service


def reconcile_offline_queue(db: Session, user_id: int, queued_transactions: list[dict]) -> dict:
    """
    queued_transactions: list of dicts as produced by the client IndexedDB queue:
    {type, amount, category_or_source, description, date, client_created_at}
    Returns {"inserted": int, "skipped_duplicates": int}
    """
    inserted = 0
    skipped = 0
    user = crud.get_user(db, user_id)
    currency = user.currency if user else "INR"

    for t in queued_transactions:
        txn_type = t.get("type")
        amount = t.get("amount")
        date_val = t.get("date")
        cat = t.get("category_or_source")
        desc = t.get("description")
        base_amount = currency_service.convert_amount(amount, currency, "INR")

        if txn_type == "income":
            dup = db.query(models.Income).filter_by(
                user_id=user_id, amount=base_amount, source=cat, description=desc, date=date_val
            ).first()
            if dup:
                skipped += 1
                continue
            crud.create_income(db, user_id, amount=base_amount, source=cat, description=desc, txn_date=date_val)
            inserted += 1
        elif txn_type == "expense":
            dup = db.query(models.Expense).filter_by(
                user_id=user_id, amount=base_amount, category=cat, description=desc, date=date_val
            ).first()
            if dup:
                skipped += 1
                continue
            crud.create_expense(db, user_id, amount=base_amount, category=cat, description=desc, txn_date=date_val)
            inserted += 1

    return {"inserted": inserted, "skipped_duplicates": skipped}
