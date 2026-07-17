"""
api/finance.py
The chat endpoint (Stash's brain meets the wire), plus dashboard and
timeline data endpoints, plus the correction-confirmation endpoint.
All scoped to the logged-in user via get_current_user.
"""

from datetime import date as DateType

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.database import get_db
from app.database import crud, models
from app.auth.auth import get_current_user
from app.ai import parser as ai_parser
from app.services import finance, analytics
from app.services import currency as currency_service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ConfirmCorrectionRequest(BaseModel):
    transaction_id: int
    transaction_type: str  # "income" | "expense"
    new_amount: float


class ConfirmDeleteRequest(BaseModel):
    transaction_id: int
    transaction_type: str  # "income" | "expense"


class TransactionUpdateRequest(BaseModel):
    amount: float | None = None
    category_or_source: str | None = None
    description: str | None = None
    date: DateType | None = None


def _serialize_transaction(row, transaction_type: str, currency: str | None) -> dict:
    if transaction_type == "income":
        label = row.source
        display_label = crud.resolve_display_label("income", row.source, row.description)
    else:
        label = row.category
        display_label = crud.resolve_display_label("expense", row.category, row.description)
    return {
        "id": row.id,
        "type": transaction_type,
        "amount": currency_service.convert_amount(row.amount, "INR", currency),
        "label": label,
        "display_label": display_label,
        "description": row.description,
        "date": str(row.date),
    }


@router.post("/chat")
def chat(payload: ChatRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    crud.save_chat_message(db, user.id, "user", payload.message)
    result = ai_parser.handle_message(payload.message, db, user.id)
    crud.save_chat_message(db, user.id, "assistant", result["reply"])

    response = dict(result)
    response["balance"] = currency_service.convert_amount(crud.get_balance(db, user.id), "INR", user.currency)
    response["currency"] = user.currency or "INR"
    if result.get("intent") in ("transaction", "correction"):
        response["suggestion"] = analytics.get_smart_suggestion(db, user)
    return response


@router.post("/chat/confirm-correction")
def confirm_correction(payload: ConfirmCorrectionRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    result = finance.confirm_correction(
        db, user.id, payload.transaction_id, payload.transaction_type, payload.new_amount, currency=user.currency
    )
    crud.save_chat_message(db, user.id, "assistant", result["reply"])
    result["balance"] = currency_service.convert_amount(crud.get_balance(db, user.id), "INR", user.currency)
    result["currency"] = user.currency or "INR"
    result["suggestion"] = analytics.get_smart_suggestion(db, user)
    return result


@router.post("/chat/confirm-delete")
def confirm_delete(payload: ConfirmDeleteRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if payload.transaction_type == "income":
        row = crud.delete_income(db, user.id, payload.transaction_id)
    elif payload.transaction_type == "expense":
        row = crud.delete_expense(db, user.id, payload.transaction_id)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transaction type")

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    db.query(models.RecurringPosting).filter(
        models.RecurringPosting.transaction_type == payload.transaction_type,
        models.RecurringPosting.transaction_id == payload.transaction_id,
    ).delete(synchronize_session=False)
    db.commit()

    balance = crud.get_balance(db, user.id)
    reply = f"Deleted {crud.resolve_display_label(payload.transaction_type, row.source if payload.transaction_type == 'income' else row.category, row.description)}."
    reply += f"\nUpdated balance: {finance._fmt_money(user.currency, balance)}"
    if balance <= 0:
        reply += f"\nYour balance hit {finance._fmt_money(user.currency, 0)}."
    crud.save_chat_message(db, user.id, "assistant", reply)
    result = {
        "ok": True,
        "reply": reply,
        "balance": balance,
        "currency": user.currency or "INR",
        "suggestion": analytics.get_smart_suggestion(db, user),
    }
    return result


@router.get("/chat/history")
def chat_history(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = crud.get_recent_chat(db, user.id, limit=50)
    return [{"role": r.role, "content": r.content, "created_at": str(r.created_at)} for r in rows]


@router.get("/pending")
def pending_entries(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Chat messages queued because both Groq and OpenRouter were down when
    first sent. The background job in main.py retries these automatically -
    this endpoint just lets the UI show 'N waiting to sync'."""
    rows = crud.get_pending_entries_for_user(db, user.id, limit=20)
    return [
        {"id": r.id, "raw_message": r.raw_message, "created_at": str(r.created_at)}
        for r in rows
    ]


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return analytics.get_dashboard_data(db, user)


@router.get("/timeline")
def timeline(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = crud.get_timeline(db, user.id, limit=200)
    return [
        {
            "id": t["id"],
            "type": t["type"],
            "amount": currency_service.convert_amount(t["amount"], "INR", user.currency),
            "label": t["label"],
            "display_label": t.get("display_label") or t["label"],
            "description": t["description"],
            "date": str(t["date"]),
        }
        for t in rows
    ]


@router.put("/transactions/{transaction_type}/{transaction_id}")
def update_transaction(
    transaction_type: str,
    transaction_id: int,
    payload: TransactionUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    if transaction_type == "income":
        fields = {}
        if "amount" in data:
            fields["amount"] = currency_service.convert_amount(data["amount"], user.currency, "INR")
        if "category_or_source" in data:
            next_source = data["category_or_source"].strip()
            if not next_source:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source cannot be empty")
            fields["source"] = next_source
        if "description" in data:
            fields["description"] = data["description"]
        if "date" in data:
            fields["date"] = data["date"]
        row = crud.update_income(db, user.id, transaction_id, **fields)
    elif transaction_type == "expense":
        fields = {}
        if "amount" in data:
            fields["amount"] = currency_service.convert_amount(data["amount"], user.currency, "INR")
        if "category_or_source" in data:
            next_category = data["category_or_source"].strip()
            if not next_category:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category cannot be empty")
            fields["category"] = next_category
        if "description" in data:
            fields["description"] = data["description"]
        if "date" in data:
            fields["date"] = data["date"]
        row = crud.update_expense(db, user.id, transaction_id, **fields)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transaction type")

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    return {"ok": True, "transaction": _serialize_transaction(row, transaction_type, user.currency)}


@router.delete("/transactions/{transaction_type}/{transaction_id}")
def delete_transaction(
    transaction_type: str,
    transaction_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if transaction_type == "income":
        row = crud.delete_income(db, user.id, transaction_id)
    elif transaction_type == "expense":
        row = crud.delete_expense(db, user.id, transaction_id)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transaction type")

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    db.query(models.RecurringPosting).filter(
        models.RecurringPosting.transaction_type == transaction_type,
        models.RecurringPosting.transaction_id == transaction_id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}
