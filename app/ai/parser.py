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
    """Last-resort fallback ONLY - used when extraction returned nothing at
    all AND no clarification_question came back either (e.g. the model
    genuinely gave no signal). Whenever the extractor supplies its own
    clarification_question, that must be used instead of this - this
    generic guesser has no idea what the actual ambiguity was about."""
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


def handle_message(message: str, db: Session, user_id: int, payment_method_hint: str | None = None) -> dict:
    """
    Returns a dict shaped as:
    {
      "intent": str,
      "reply": str,                # text Stash says back
      "data": dict | list | None,  # structured payload for the UI (e.g. created txn)
      "needs_confirmation": bool,  # True if a correction/extraction is ambiguous and needs user pick
      "candidates": list | None,   # disambiguation options if needs_confirmation
    }

    payment_method_hint: explicit Cash/Online selection from the chat
    composer's toggle (#33-35). Only fills in transactions where the
    extractor found no textual signal at all - explicit words in the
    message ("paid cash for tea") always take priority over the toggle,
    since the toggle is a fallback default, not an override of what the
    user actually typed.
    """
    from app.services import finance  # local import to avoid circular import

    user = crud.get_user(db, user_id)
    currency = user.currency if user else "INR"
    recent_chat = _recent_chat_memory(db, user_id, message)

    try:
        intent = intent_detector.detect_intent(message, recent_chat=recent_chat or None)
    except LLMUnavailableError:
        return _queue_for_later(db, user_id, message)

    if intent == "transaction":
        user_hints = [(m.keyword, m.category_or_source) for m in crud.get_top_merchant_memories(db, user_id)]
        try:
            extraction = extractor.extract_transactions(message, recent_chat=recent_chat or None, user_hints=user_hints or None)
        except LLMUnavailableError:
            return _queue_for_later(db, user_id, message)

        # extractor.extract_transactions is expected to return a dict shaped like:
        # {"transactions": [...], "clarification_needed": bool, "clarification_question": str|None}
        # matching prompts.EXTRACTION_SYSTEM_PROMPT's JSON schema.
        transactions = extraction.get("transactions", [])
        clarification_needed = extraction.get("clarification_needed", False)
        clarification_question = extraction.get("clarification_question")

        if payment_method_hint:
            for txn in transactions:
                if not txn.get("payment_method"):
                    txn["payment_method"] = payment_method_hint

        # Truly nothing extracted and no clarification offered either - only
        # here do we fall back to the generic guesser.
        if not transactions and not clarification_needed:
            return {
                "intent": "chat",
                "reply": _clarify_amount(message),
                "data": None, "needs_confirmation": False, "candidates": None,
            }

        created = []
        if transactions:
            created = finance.create_transactions(db, user_id, transactions, currency=currency)

        if clarification_needed and clarification_question:
            balance = finance.crud.get_balance(db, user_id)
            reply_text = clarification_question

            # Expense Prediction (#29) - offer the user's own learned habit
            # as a suggested default before they have to answer manually,
            # rather than a bare open-ended question with no starting point.
            keywords = finance._distinctive_keywords(message)
            if keywords:
                for txn_type in ("expense", "income"):
                    predicted = crud.recall_merchant_category(db, user_id, txn_type, keywords, min_hits=2)
                    if predicted:
                        reply_text = f"{clarification_question} (My best guess based on your past entries: {predicted} - just confirm or tell me the right one.)"
                        break

            if created:
                # Confirm what WAS logged before asking about the ambiguous part,
                # so the user sees both in one reply instead of a bare question.
                logged_summary = finance.format_transaction_reply(created, balance=balance, currency=currency)
                reply_text = f"{logged_summary}\n\n{reply_text}"
            return {
                "intent": "transaction",
                "reply": reply_text,
                "data": created,
                # NOT True: needs_confirmation elsewhere in this file always
                # pairs with a populated `candidates` list that the frontend
                # renders as pick buttons (see correction/delete). This is a
                # free-text follow-up question instead (the user just types
                # a reply, same as any other chat message), so keep this
                # False to avoid triggering picker UI with candidates=None.
                "needs_confirmation": False,
                "candidates": None,
            }

        balance = finance.crud.get_balance(db, user_id)
        return {
            "intent": "transaction",
            "reply": finance.format_transaction_reply(created, balance=balance, currency=currency),
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
        result = finance.apply_correction(db, user_id, correction, currency=currency)
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
        result = finance.apply_delete(db, user_id, delete_request, currency=currency)
        return result

    if intent == "question":
        # "Why did you categorize/classify/call this X" - answered from the
        # actual deterministic rule that ran (#26), not a generic LLM guess.
        lowered_msg = message.lower()
        if "why" in lowered_msg and any(w in lowered_msg for w in ("categor", "classif", "call it", "call this", "put it", "put this", "mark it", "mark this")):
            return {
                "intent": "question", "reply": finance.explain_last_categorization(db, user_id),
                "data": None, "needs_confirmation": False, "candidates": None,
            }
        context = finance.build_qa_context(db, user_id, message, currency=currency)
        try:
            answer = response.answer_question(message, context)
        except LLMUnavailableError:
            return _queue_for_later(db, user_id, message)
        return {
            "intent": "question", "reply": answer, "data": context,
            "needs_confirmation": False, "candidates": None,
        }

    if intent == "report":
        report = finance.build_report(db, user_id, message, currency=currency)
        return {
            "intent": "report", "reply": report["summary_text"], "data": report,
            "needs_confirmation": False, "candidates": None,
        }

    # chat fallback - greetings, thanks, jokes, "what can you do" (#25, #31, #32)
    return {
        "intent": "chat",
        "reply": response.casual_reply(message, recent_chat=recent_chat or None),
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