"""
extractor.py
Extracts structured transaction(s) or correction details from natural language,
using the cloud LLM (Groq/OpenRouter), with date-hint resolution into real dates.

Two bugs this file specifically fixes vs the original single-user version:
1. Category resolution used to fall back to keyword-matching the WHOLE raw
   message when the LLM's guess didn't exactly match the valid list. For a
   multi-transaction message ("Salary 35000, Petrol 400, Tea 20"), that meant
   the Petrol line could get contaminated by the word "tea" elsewhere in the
   message. Matching now happens against the LLM's own per-transaction guess
   (and that transaction's description) first, never the full raw message.
2. resolve_date_hint() only understood "today"/"yesterday"/weekday
   names/explicit dates - "2 days ago" fell through silently to today. Added
   regex handling for "N day(s) ago/back", "day before yesterday", and
   "last <weekday>".
"""

import re
from datetime import date, timedelta

from . import llm
from .prompts import (
    CATEGORIES_EXPENSE,
    CATEGORIES_INCOME,
    CORRECTION_SYSTEM_PROMPT,
    DELETE_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

EXPENSE_CATEGORY_HINTS = {
    "Tea": ("tea", "coffee", "chai"),
    "Snacks": ("snack", "snacks"),
    "Food": ("food", "meal", "eating", "restaurant", "canteen", "tiffin", "lunch", "dinner", "breakfast"),
    "Groceries": ("grocery", "groceries", "vegetable", "vegetables", "fruit", "fruits", "milk", "bread", "rice", "eggs"),
    "Petrol": ("petrol", "fuel", "gas", "diesel"),
    "Shopping": ("shopping", "amazon", "flipkart", "myntra", "order", "purchase", "clothes", "shirt", "pants", "shoes"),
    "Bills": ("bill", "bills", "electricity", "power", "water", "internet", "wifi", "rent", "subscription", "mobile recharge", "recharge"),
    "Travel": ("travel", "cab", "taxi", "uber", "ola", "bus", "train", "metro", "flight", "ticket"),
    "Entertainment": ("movie", "movies", "cinema", "game", "games", "concert", "party", "fun"),
    "Medical": ("medical", "doctor", "medicine", "pharmacy", "hospital", "clinic", "checkup", "treatment"),
    "Education": ("education", "school", "college", "tuition", "fee", "course", "books", "exam"),
    "Investment": ("investment", "invest", "sip", "stocks", "shares", "mutual fund", "fd", "gold", "crypto"),
}

INCOME_CATEGORY_HINTS = {
    "Salary": ("salary", "paycheck", "pay slip", "pay", "wage", "wages"),
    "Freelance": ("freelance", "gig", "project", "invoice", "client"),
    "Gift": ("gift", "gifts", "gifted", "present"),
    "Refund": ("refund", "returned", "cashback", "reimburs", "reimburse"),
}

_DAYS_AGO_RE = re.compile(r"(\d+)\s*(?:day|days)\s*(?:ago|back)")
_WEEKS_AGO_RE = re.compile(r"(\d+)\s*(?:week|weeks)\s*(?:ago|back)")
_ORDINAL_SUFFIX_RE = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)


def _normalize_date_text(text: str) -> str:
    return _ORDINAL_SUFFIX_RE.sub(r"\1", text)


def _memory_block(recent_chat: str | None) -> str:
    if not recent_chat:
        return ""
    return f"RECENT CHAT MEMORY:\n{recent_chat.strip()}\n\n"


def resolve_date_hint(hint: str | None) -> date:
    """Best-effort conversion of a natural language date hint into a real date.
    Falls back to today if the hint is missing or unparseable."""
    if not hint:
        return date.today()
    cleaned_hint = _normalize_date_text(hint.strip())
    h = cleaned_hint.lower()
    today = date.today()

    if h in ("today", "now"):
        return today
    if h == "yesterday":
        return today - timedelta(days=1)
    if h in ("day before yesterday", "the day before yesterday"):
        return today - timedelta(days=2)

    days_ago_match = _DAYS_AGO_RE.search(h)
    if days_ago_match:
        return today - timedelta(days=int(days_ago_match.group(1)))

    weeks_ago_match = _WEEKS_AGO_RE.search(h)
    if weeks_ago_match:
        return today - timedelta(weeks=int(weeks_ago_match.group(1)))

    if "last week" in h:
        return today - timedelta(weeks=1)

    for weekday_name in WEEKDAYS:
        if weekday_name in h:
            target_idx = WEEKDAYS.index(weekday_name)
            delta = (today.weekday() - target_idx) % 7
            # "last monday" always means the previous occurrence, even if
            # today happens to be monday; plain "monday" means the most
            # recent past monday (today if delta==0 is unusual for a
            # transaction message, so treat delta==0 as 7 days back only
            # when the word "last" is present).
            if delta == 0 and "last" in h:
                delta = 7
            return today - timedelta(days=delta)

    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d",
        "%b %d",
        "%d %B",
        "%d %b",
    ):
        try:
            from datetime import datetime

            parsed = datetime.strptime(cleaned_hint, fmt)
            if "%Y" not in fmt:
                parsed = parsed.replace(year=today.year)
            return parsed.date()
        except ValueError:
            continue
    return today


def _match_hint(text: str, hint_map: dict) -> str | None:
    """Finds the category whose hint keywords appear in `text`, preferring
    the LONGEST matching keyword (so 'restaurant' beats a stray 'tea' match,
    and overlapping keywords like 'snack' don't randomly favor whichever
    category happens to be first in the dict)."""
    lowered = text.lower()
    best_category = None
    best_len = 0
    for category, hints in hint_map.items():
        for hint in hints:
            if hint in lowered and len(hint) > best_len:
                best_category = category
                best_len = len(hint)
    return best_category


def _resolve_category_or_source(txn_type: str, raw_value: str | None, description: str | None) -> str:
    valid_list = CATEGORIES_INCOME if txn_type == "income" else CATEGORIES_EXPENSE
    hint_map = INCOME_CATEGORY_HINTS if txn_type == "income" else EXPENSE_CATEGORY_HINTS

    if raw_value:
        raw_clean = raw_value.strip()
        # Case-insensitive exact match against the valid list first.
        for candidate in valid_list:
            if candidate.lower() == raw_clean.lower():
                return candidate
        # LLM gave a near-miss word (e.g. "Coffee", "Restaurant bill") that
        # isn't itself a valid category - map it via keyword hints, scoped
        # to the LLM's own guess text, never the full raw message.
        matched = _match_hint(raw_clean, hint_map)
        if matched:
            return matched

    # Last resort: use this transaction's own description (still not the
    # full multi-transaction message, so no cross-contamination).
    if description:
        matched = _match_hint(description, hint_map)
        if matched:
            return matched

    return "Other"


def extract_transactions(message: str, recent_chat: str | None = None) -> list[dict]:
    """Returns a list of dicts: {type, amount, category_or_source, description, date}.
    Raises llm.LLMUnavailableError if both Groq and OpenRouter are down -
    callers must catch that specifically and queue the message rather than
    treating it as 'not a transaction'."""
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"{_memory_block(recent_chat)}MESSAGE:\n{message}"},
    ]
    raw = llm.fast_chat(messages, json_mode=True, max_tokens=400)

    parsed = llm.safe_json_parse(raw)

    if not parsed or "transactions" not in parsed:
        return []

    results = []
    for t in parsed["transactions"]:
        try:
            amount = float(t.get("amount"))
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue

        txn_type = t.get("type") if t.get("type") in ("income", "expense") else "expense"
        description = t.get("description") or message.strip()
        cat = _resolve_category_or_source(
            txn_type,
            t.get("category_or_source"),
            description,
        )

        results.append({
            "type": txn_type,
            "amount": amount,
            "category_or_source": cat,
            "description": description,
            "date": resolve_date_hint(t.get("date_hint")),
        })
    return results


def extract_correction(message: str, recent_chat: str | None = None) -> dict | None:
    """Raises llm.LLMUnavailableError if both providers are down."""
    messages = [
        {"role": "system", "content": CORRECTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"{_memory_block(recent_chat)}MESSAGE:\n{message}"},
    ]
    raw = llm.fast_chat(messages, json_mode=True, max_tokens=250)

    parsed = llm.safe_json_parse(raw)
    if not parsed:
        return None
    try:
        new_amount = float(parsed.get("new_amount"))
    except (TypeError, ValueError):
        return None
    if new_amount <= 0:
        return None

    txn_type = parsed.get("type") if parsed.get("type") in ("income", "expense") else "expense"
    return {
        "type": txn_type,
        "category_or_source": _resolve_category_or_source(
            txn_type,
            parsed.get("category_or_source"),
            parsed.get("search_terms"),
        ),
        "new_amount": new_amount,
        "date": resolve_date_hint(parsed.get("date_hint")),
        "search_terms": parsed.get("search_terms") or "",
    }


def extract_delete(message: str, recent_chat: str | None = None) -> dict | None:
    """Raises llm.LLMUnavailableError if both providers are down."""
    messages = [
        {"role": "system", "content": DELETE_SYSTEM_PROMPT},
        {"role": "user", "content": f"{_memory_block(recent_chat)}MESSAGE:\n{message}"},
    ]
    raw = llm.fast_chat(messages, json_mode=True, max_tokens=220)

    parsed = llm.safe_json_parse(raw)
    if not parsed:
        return None

    txn_type = parsed.get("type") if parsed.get("type") in ("income", "expense") else "expense"
    return {
        "type": txn_type,
        "category_or_source": _resolve_category_or_source(
            txn_type,
            parsed.get("category_or_source"),
            parsed.get("search_terms"),
        ),
        "date": resolve_date_hint(parsed.get("date_hint")),
        "search_terms": parsed.get("search_terms") or "",
    }
