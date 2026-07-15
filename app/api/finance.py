"""
api/finance.py
The chat endpoint (Stash's brain meets the wire), plus dashboard and
timeline data endpoints, plus the correction-confirmation endpoint.
All scoped to the logged-in user via get_current_user.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.database import get_db
from app.database import crud, models
from app.auth.auth import get_current_user
from app.ai import parser as ai_parser
from app.services import finance, analytics

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ConfirmCorrectionRequest(BaseModel):
    transaction_id: int
    transaction_type: str  # "income" | "expense"
    new_amount: float


@router.post("/chat")
def chat(payload: ChatRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    crud.save_chat_message(db, user.id, "user", payload.message)
    result = ai_parser.handle_message(payload.message, db, user.id)
    crud.save_chat_message(db, user.id, "assistant", result["reply"])

    response = dict(result)
    response["balance"] = crud.get_balance(db, user.id)
    response["currency"] = user.currency or "INR"
    if result.get("intent") in ("transaction", "correction"):
        response["suggestion"] = analytics.get_smart_suggestion(db, user)
    return response


@router.post("/chat/confirm-correction")
def confirm_correction(payload: ConfirmCorrectionRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    result = finance.confirm_correction(
        db, user.id, payload.transaction_id, payload.transaction_type, payload.new_amount
    )
    crud.save_chat_message(db, user.id, "assistant", result["reply"])
    result["balance"] = crud.get_balance(db, user.id)
    result["currency"] = user.currency or "INR"
    result["suggestion"] = analytics.get_smart_suggestion(db, user)
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
            "amount": t["amount"],
            "label": t["label"],
            "display_label": t.get("display_label") or t["label"],
            "description": t["description"],
            "date": str(t["date"]),
        }
        for t in rows
    ]
