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

A third change (see extract_transactions): the function now returns the
FULL parsed shape - transactions plus clarification_needed/
clarification_question - instead of a bare list. Previously those two
fields were parsed by the LLM but silently discarded here, which meant
genuinely ambiguous amounts (e.g. "half" with more than one plausible base)
never reached the user as a real question - the caller only saw an empty
or partial transaction list and fell back to a generic hardcoded prompt.
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
    GOAL_SYSTEM_PROMPT,
)

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

EXPENSE_CATEGORY_HINTS = {
    "Tea": ("tea", "coffee", "chai", "cafe coffee day", "ccd", "starbucks", "chaayos"),
    "Snacks": ("snack", "snacks"),
    "Food": (
        "food", "meal", "eating", "restaurant", "canteen", "tiffin", "lunch", "dinner", "breakfast",
        # merchant semantic matching (#17) - same "Food" category regardless
        # of which delivery/restaurant brand is actually named.
        "swiggy", "zomato", "dominos", "domino's", "pizza hut", "mcdonald", "kfc", "burger king", "subway",
    ),
    "Groceries": (
        "grocery", "groceries", "vegetable", "vegetables", "fruit", "fruits", "milk", "bread", "rice", "eggs",
        "bigbasket", "big basket", "blinkit", "zepto", "instamart", "grofers", "dmart", "d-mart", "jiomart",
    ),
    "Petrol": ("petrol", "fuel", "gas", "diesel"),
    "Shopping": (
        "shopping", "amazon", "flipkart", "myntra", "order", "purchase", "clothes", "shirt", "pants", "shoes",
        "ajio", "nykaa", "meesho",
    ),
    "Bills": (
        "bill", "bills", "electricity", "power", "water", "internet", "wifi", "rent", "subscription",
        "mobile recharge", "recharge",
        "netflix", "spotify", "prime video", "amazon prime", "hotstar", "disney+", "airtel", "jio", "vodafone",
    ),
    "Travel": (
        "travel", "cab", "taxi", "uber", "ola", "bus", "train", "metro", "flight", "ticket",
        "rapido", "irctc", "indigo", "makemytrip", "goibibo",
    ),
    "Entertainment": ("movie", "movies", "cinema", "game", "games", "concert", "party", "fun", "bookmyshow", "pvr", "inox"),
    "Medical": ("medical", "doctor", "medicine", "pharmacy", "hospital", "clinic", "checkup", "treatment", "pharmeasy", "1mg", "apollo pharmacy", "netmeds"),
    "Education": ("education", "school", "college", "tuition", "fee", "course", "books", "exam", "byju", "udemy", "coursera"),
    "Investment": ("investment", "invest", "sip", "stocks", "shares", "mutual fund", "fd", "gold", "crypto", "zerodha", "groww", "upstox"),
}

INCOME_CATEGORY_HINTS = {
    "Salary": ("salary", "paycheck", "pay slip", "pay", "wage", "wages"),
    "Freelance": ("freelance", "gig", "project", "invoice", "client"),
    "Gift": (
        "gift", "gifts", "gifted", "present",
        # Money received from a relative/friend with no other stated source
        # reads as a gift, not "Other" - e.g. "got 4000 from uncle".
        "uncle", "aunt", "aunty", "grandma", "grandpa", "grandmother", "grandfather",
        "mom", "dad", "mother", "father", "parents", "brother", "sister",
        "relative", "cousin", "friend gave", "friend transferred",
    ),
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


def _habits_block(user_hints: list[tuple[str, str]] | None) -> str:
    """Feature #30 Adaptive Prompting - renders the user's own learned
    merchant habits (see crud.get_top_merchant_memories) into the prompt
    so the LLM's OWN category guess adapts to this specific user's
    history, not just the deterministic post-hoc override in
    services/finance.py. Advisory only - the prompt still lets the LLM
    override with a stronger literal cue in the message itself."""
    if not user_hints:
        return ""
    lines = "\n".join(f'- "{keyword}" has usually meant {category} for this user' for keyword, category in user_hints)
    return (
        "THIS USER'S OWN PAST HABITS (use as a soft prior when the message doesn't clearly say otherwise - "
        "an explicit category/merchant in the message itself still wins over this):\n" + lines + "\n\n"
    )


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


def explain_category(txn_type: str, category_or_source: str, description: str | None) -> tuple[str, str | None]:
    """Feature #26 - Explain AI Decisions. Recomputes, against the SAME
    hint tables used at extraction time, whether the category came from a
    recognizable keyword. Returns (reason_kind, keyword):
      - ("hint_match", keyword)   - description contains a known keyword/merchant
      - ("no_match", None)        - no keyword matched; category_or_source was
                                     either explicitly stated or an LLM guess
    Deliberately does NOT talk to the LLM or the DB - this must describe
    the actual deterministic rule that ran, not a plausible-sounding story
    made up after the fact. Personalized-memory reasons (learned habits)
    are checked separately in services/finance.py, which has DB access."""
    if not description:
        return ("no_match", None)
    hint_map = INCOME_CATEGORY_HINTS if txn_type == "income" else EXPENSE_CATEGORY_HINTS
    hints = hint_map.get(category_or_source, ())
    lowered = description.lower()
    matched_keyword = None
    best_len = 0
    for hint in hints:
        if hint in lowered and len(hint) > best_len:
            matched_keyword = hint
            best_len = len(hint)
    if matched_keyword:
        return ("hint_match", matched_keyword)
    return ("no_match", None)


def extract_transactions(message: str, recent_chat: str | None = None, user_hints: list[tuple[str, str]] | None = None) -> dict:
    """Returns a dict: {"transactions": list[dict], "clarification_needed": bool,
    "clarification_question": str | None}. Each transaction dict is
    {type, amount, category_or_source, description, date}.

    user_hints: optional list of (keyword, category_or_source) pairs - this
    user's own strongest learned habits (#30 Adaptive Prompting) - fed into
    the prompt as a soft prior so the LLM's first guess adapts to this
    user's history, not just the deterministic override that runs later.

    NOTE: this used to return a bare list[dict]. It now returns the full
    shape so callers (parser.py) can see when the model deliberately held
    a transaction back due to genuine ambiguity (e.g. "half of what's left"
    when there's more than one plausible base amount) instead of that
    signal being silently dropped.

    Raises llm.LLMUnavailableError if both Groq and OpenRouter are down -
    callers must catch that specifically and queue the message rather than
    treating it as 'not a transaction'."""
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"{_habits_block(user_hints)}{_memory_block(recent_chat)}MESSAGE:\n{message}"},
    ]
    raw = llm.fast_chat(messages, json_mode=True, max_tokens=400)

    parsed = llm.safe_json_parse(raw)

    if not parsed or "transactions" not in parsed:
        return {"transactions": [], "clarification_needed": False, "clarification_question": None}

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

        payment_method = t.get("payment_method")
        if payment_method not in ("cash", "online"):
            payment_method = None

        results.append({
            "type": txn_type,
            "amount": amount,
            "category_or_source": cat,
            "description": description,
            "date": resolve_date_hint(t.get("date_hint")),
            "payment_method": payment_method,
        })

    clarification_needed = bool(parsed.get("clarification_needed", False))
    clarification_question = parsed.get("clarification_question") or None
    # Don't claim clarification is needed if the model set the flag but gave
    # no actual question text - that's not something parser.py can show the
    # user, so treat it the same as "nothing to clarify".
    if clarification_needed and not clarification_question:
        clarification_needed = False

    _reconcile_split_total(results, parsed.get("split_total"))

    return {
        "transactions": results,
        "clarification_needed": clarification_needed,
        "clarification_question": clarification_question,
    }


def _reconcile_split_total(results: list[dict], split_total) -> None:
    """When the model split one stated total across several categorized
    transactions (feature: automatic itemized-purchase splitting), its
    per-item arithmetic can be off by a few cents/rupees due to rounding.
    Rather than trust that silently, snap the split to add up EXACTLY to
    the total the user actually stated - the largest line absorbs the
    difference, since a rounding correction is least noticeable there.
    No-op unless split_total is a positive number and there are at least
    2 transactions of the same type to split across."""
    try:
        total = float(split_total)
    except (TypeError, ValueError):
        return
    if total <= 0 or len(results) < 2:
        return

    # Only reconcile within a single type - a split is always same-type
    # (e.g. groceries + medicine), never income mixed with expense.
    for txn_type in ("expense", "income"):
        group = [r for r in results if r["type"] == txn_type]
        if len(group) < 2:
            continue
        group_sum = sum(r["amount"] for r in group)
        # Only treat this as "the" split group if it's plausibly the whole
        # total (within 50%) - otherwise split_total likely refers to a
        # different subset of the message and correcting here would be a
        # bigger guess than the drift it's meant to fix.
        if group_sum <= 0 or abs(group_sum - total) > total * 0.5:
            continue
        diff = round(total - group_sum, 2)
        if diff == 0:
            continue
        largest = max(group, key=lambda r: r["amount"])
        largest["amount"] = round(largest["amount"] + diff, 2)


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

def resolve_goal_deadline(hint: str | None) -> date | None:
    """Parses a savings-goal DEADLINE (a future date), which is a different
    problem from resolve_date_hint (always resolves PAST transaction
    dates) - reusing that function here would silently misinterpret "by
    December" as today. Returns None (no deadline) rather than guessing
    when the phrase isn't recognized - a wrong invented deadline is worse
    than no deadline at all for a savings goal."""
    if not hint:
        return None
    h = hint.strip().lower()
    today = date.today()

    if "this month" in h:
        y, m = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
        return date(y, m, 1) - timedelta(days=1)
    if "next month" in h:
        y, m = (today.year, today.month + 2) if today.month < 11 else (today.year + 1, today.month - 10)
        return date(y, m, 1) - timedelta(days=1)

    months_match = re.search(r"in\s+(\d+)\s+months?", h)
    if months_match:
        n = int(months_match.group(1))
        total = today.month - 1 + n
        y = today.year + total // 12
        m = total % 12 + 1
        return date(y, m, 1)

    for idx, name in enumerate(MONTH_NAMES, start=1):
        if re.search(rf"\b{name}\b", h):
            year = today.year if idx >= today.month else today.year + 1
            return date(year, idx, 1)

    return None


def extract_goal(message: str) -> dict:
    """Feature: Financial Goal Tracking. Returns {"target_amount": float|None,
    "target_date": date|None}. Raises llm.LLMUnavailableError if both
    providers are down - callers should queue/retry rather than silently
    failing to set the goal."""
    messages = [
        {"role": "system", "content": GOAL_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    raw = llm.fast_chat(messages, json_mode=True, max_tokens=80)
    parsed = llm.safe_json_parse(raw) or {}
    target_amount = parsed.get("target_amount")
    try:
        target_amount = float(target_amount) if target_amount is not None else None
    except (TypeError, ValueError):
        target_amount = None
    return {
        "target_amount": target_amount,
        "target_date": resolve_goal_deadline(parsed.get("date_hint")),
    }
