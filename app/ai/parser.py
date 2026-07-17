"""
parser.py
Top-level orchestrator called by the chat API route. Given a raw user
message, it detects intent and routes to the right handler, returning a
structured result the API layer turns into a chat bubble + UI update.

This module deliberately does NOT touch the DB directly for transaction
data - it delegates to services.finance, which owns transaction read/write
and disambiguation. It DOES touch the DB for the pending_entries queue,
since that's this module's own responsibility (catching LLM outages).
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from . import extractor, intent_detector, response
from .llm import LLMUnavailableError
from app.database import crud

_WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()
_DATE_HINT_PATTERNS = [
    r"\bday before yesterday\b",
    r"\bthe day before yesterday\b",
    r"\btoday\b",
    r"\byesterday\b",
    r"\blast week\b",
    r"\b\d+\s*(?:day|days)\s*(?:ago|back)\b",
    r"\b\d+\s*(?:week|weeks)\s*(?:ago|back)\b",
    r"\b(?:last\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+\d{4})?\b",
    r"\b[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b",
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
]


def _recent_chat_memory(db: Session, user_id: int, current_message: str) -> str:
    rows = crud.get_recent_chat(db, user_id, limit=11)
    if rows and rows[-1].role == "user" and rows[-1].content == current_message:
        rows = rows[:-1]
    rows = rows[-10:]
    if not rows:
        return ""
    lines = []
    for row in rows:
        speaker = "User" if row.role == "user" else "Assistant"
        lines.append(f"{speaker}: {row.content}")
    return "\n".join(lines)


def _guess_date_hint(message: str):
    for pattern in _DATE_HINT_PATTERNS:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return extractor.resolve_date_hint(match.group(0))
    return None


def _format_date_for_reply(value) -> str:
    return f"{value.day} {value.strftime('%B')}"


def _clarify_amount(message: str) -> str:
    lowered = message.lower()
    date_hint = _guess_date_hint(message)
    if any(word in lowered for word in ("salary", "paycheck", "wage", "wages")):
        subject = "salary"
    elif any(word in lowered for word in ("received", "got", "income", "earned", "deposit")):
        subject = "that income"
    else:
        subject = "that entry"

    if date_hint:
        return f"How much {subject} should I enter for {_format_date_for_reply(date_hint)}?"
    return f"How much {subject} should I enter?"


def handle_message(message: str, db: Session, user_id: int) -> dict:
    """
    Returns a dict shaped as:
    {
      "intent": str,
      "reply": str,                # text Stash says back
      "data": dict | list | None,  # structured payload for the UI (e.g. created txn)
      "needs_confirmation": bool,  # True if a correction is ambiguous and needs user pick
      "candidates": list | None,   # disambiguation options if needs_confirmation
    }
    """
    from app.services import finance  # local import to avoid circular import

    recent_chat = _recent_chat_memory(db, user_id, message)

    try:
        intent = intent_detector.detect_intent(message, recent_chat=recent_chat or None)
    except LLMUnavailableError:
        return _queue_for_later(db, user_id, message)

    if intent == "transaction":
        try:
            transactions = extractor.extract_transactions(message, recent_chat=recent_chat or None)
        except LLMUnavailableError:
            return _queue_for_later(db, user_id, message)

        if not transactions:
            return {
                "intent": "chat",
                "reply": _clarify_amount(message),
                "data": None, "needs_confirmation": False, "candidates": None,
            }
        created = finance.create_transactions(db, user_id, transactions)
        balance = finance.crud.get_balance(db, user_id)
        return {
            "intent": "transaction",
            "reply": finance.format_transaction_reply(created, balance=balance),
            "data": created,
            "needs_confirmation": False,
            "candidates": None,
        }

    if intent == "correction":
        try:
            correction = extractor.extract_correction(message, recent_chat=recent_chat or None)
        except LLMUnavailableError:
            return _queue_for_later(db, user_id, message)

        if not correction:
            return {
                "intent": "chat",
                "reply": "I couldn't tell what to correct - try something like 'petrol was actually 600'.",
                "data": None, "needs_confirmation": False, "candidates": None,
            }
        result = finance.apply_correction(db, user_id, correction)
        return result

    if intent == "delete":
        try:
            delete_request = extractor.extract_delete(message, recent_chat=recent_chat or None)
        except LLMUnavailableError:
            return _queue_for_later(db, user_id, message)

        if not delete_request:
            return {
                "intent": "chat",
                "reply": "I couldn't tell which entry to delete - try something like 'delete yesterday's tea entry'.",
                "data": None, "needs_confirmation": False, "candidates": None,
            }
        result = finance.apply_delete(db, user_id, delete_request)
        return result

    if intent == "question":
        context = finance.build_qa_context(db, user_id, message)
        try:
            answer = response.answer_question(message, context)
        except LLMUnavailableError:
            return _queue_for_later(db, user_id, message)
        return {
            "intent": "question", "reply": answer, "data": context,
            "needs_confirmation": False, "candidates": None,
        }

    if intent == "report":
        report = finance.build_report(db, user_id, message)
        return {
            "intent": "report", "reply": report["summary_text"], "data": report,
            "needs_confirmation": False, "candidates": None,
        }

    # chat fallback
    return {
        "intent": "chat",
        "reply": "Hi, I'm Stash - tell me what happened, for example 'Salary received 35000' or 'Tea 20'.",
        "data": None, "needs_confirmation": False, "candidates": None,
    }


def _queue_for_later(db: Session, user_id: int, message: str) -> dict:
    """Both Groq and OpenRouter are unavailable. Rather than losing the
    message or wrongly telling the user 'that's not a transaction', save it
    to pending_entries - a background job (see main.py) retries it every 5
    minutes and posts it automatically once a provider is back up."""
    crud.create_pending_entry(db, user_id, message)
    return {
        "intent": "chat",
        "reply": (
            "Both AI providers are busy or rate-limited right now. I've saved your message "
            "and it'll be processed automatically within a few minutes - no need to resend it."
        ),
        "data": None,
        "needs_confirmation": False,
        "candidates": None,
    }
