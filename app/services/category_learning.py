"""
category_learning.py
The "teach Stash a new item" loop that sits on top of the product glossary
(app/glossary):

  1. A transaction comes in and the glossary + LLM still can't place the
     item -> it is saved under "Other" (never lost, balance stays right).
  2. Stash asks, in the same chat reply, which category the item belongs to
     and remembers the pending question (models.PendingSelection, kind
     "categorize").
  3. The user's next message is checked FIRST against that question (no LLM
     call). A category name (or a glossary word like "sweets") moves the
     entry, and the mapping is saved per user (models.UserGlossaryTerm) so
     the same item is filed correctly from then on.

Only expenses trigger the question - income "sources" are personal (a
client's name, a relative) and asking about them would just be noise.

This module deliberately does not import services.finance (finance calls
into it), so there is no import cycle.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import glossary
from app.ai.prompts import CATEGORIES_EXPENSE
from app.database import crud
from app.services import currency as currency_service

logger = logging.getLogger(__name__)

PENDING_KIND = "categorize"
QUESTION_TTL = timedelta(hours=24)
MAX_ATTEMPTS = 2

_REPLY_FILLER = {
    "it", "its", "is", "this", "that", "put", "in", "into", "under", "as", "to", "goes", "go", "belongs",
    "belong", "category", "the", "a", "an", "should", "be", "please", "pls", "add", "mark", "file", "type",
    "kind", "of", "i", "think", "say", "call", "one", "name", "then", "yes", "yeah", "ok", "okay",
}
_SKIP_PHRASES = (
    "skip", "cancel", "ignore", "never mind", "nevermind", "dont know", "do not know", "no idea",
    "not sure", "leave it", "leave as is", "later", "dunno",
)


# ---------------------------------------------------------------------------
# Lookups used while creating a transaction
# ---------------------------------------------------------------------------

def find_taught_category(db: Session, user_id: int, txn_type: str, description: str | None):
    """The user's own taught term for this description, or None. Beats the
    built-in glossary unless the glossary matched a strictly longer phrase
    ("dahi vada" in the glossary outranks a taught "dahi")."""
    if not description:
        return None
    terms = crud.get_user_glossary_terms(db, user_id, txn_type)
    if not terms:
        return None
    index = glossary.Index()
    for term, category in terms.items():
        index.add(term, category, "taught")
    index.finalize()
    mine = glossary.resolve(description, index)
    if not mine or not mine.category:
        return None
    builtin = glossary.lookup(description, txn_type)
    if builtin and builtin.category and builtin.strength > mine.strength:
        return None
    return mine


def unknown_term_for(txn_type: str, description: str | None) -> str | None:
    """The item name worth asking the user about, or None. Anything the
    glossary has an opinion on (including "known, deliberately Other" and
    ambiguous ties) is not unknown."""
    if txn_type != "expense":
        return None
    if glossary.lookup(description, txn_type) is not None:
        return None
    return glossary.extract_unknown_term(description)


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------

def _category_choices() -> str:
    names = [c for c in CATEGORIES_EXPENSE if c != "Other"]
    return ", ".join(names) + " or Other"


def _question(term: str, first: bool = True) -> str:
    if first:
        return (
            f"I don't know what \"{term}\" is yet, so I saved it under Other for now. "
            f"Which category should it go in? {_category_choices()}. "
            f"Just reply with the category and I'll remember it for next time."
        )
    return f"Next one: \"{term}\" - which category should it go in?"


def ask_about_unknown_terms(db: Session, user_id: int, created: list[dict]) -> str | None:
    """Looks at freshly created transactions, and if any carry an
    `unknown_term` (set by finance.create_transactions), stores a pending
    question and returns the text to append to the chat reply."""
    items: list[dict] = []
    by_term: dict[str, dict] = {}
    for txn in created:
        term = txn.get("unknown_term")
        if not term or txn.get("type") != "expense":
            continue
        if term in by_term:
            by_term[term]["txn_ids"].append(txn["id"])
            continue
        item = {"term": term, "txn_ids": [txn["id"]], "attempts": 0}
        by_term[term] = item
        items.append(item)
    if not items:
        return None
    crud.set_pending_selection(db, user_id, PENDING_KIND, items)
    return _question(items[0]["term"])


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------

def _is_stale(created_at) -> bool:
    if not created_at:
        return False
    now = datetime.now(timezone.utc) if created_at.tzinfo else datetime.utcnow()
    return now - created_at > QUESTION_TTL


def resolve_category_reply(text: str) -> str | None:
    """Turns a reply like "groceries", "put it in Snacks" or "it's a sweet"
    into a valid expense category, or None if it can't be read confidently."""
    tokens = [t for t in glossary.tokenize(text) if t not in _REPLY_FILLER]
    if not tokens:
        return None
    remaining = " ".join(tokens)
    for category in CATEGORIES_EXPENSE:
        if remaining == " ".join(glossary.tokenize(category)):
            return category
    result = glossary.lookup(remaining, "expense")
    if result and result.category in CATEGORIES_EXPENSE:
        return result.category
    return None


def _looks_like_answer(text: str) -> bool:
    tokens = glossary.tokenize(text)
    return bool(tokens) and len(tokens) <= 6


def _finish(db: Session, user_id: int, rest: list[dict], lead: str) -> dict:
    if rest:
        crud.set_pending_selection(db, user_id, PENDING_KIND, rest)
        lead = f"{lead}\n\n{_question(rest[0]['term'], first=False)}"
    else:
        crud.clear_pending_selection(db, user_id)
    return {
        "intent": "transaction", "reply": lead, "data": None,
        "needs_confirmation": False, "candidates": None,
    }


def handle_answer(db: Session, user_id: int, message: str, pending: dict, currency: str | None) -> dict | None:
    """Tries to treat `message` as the answer to a pending category
    question. Returns a chat result dict if it did, or None if the message
    is really something else (the pending question is dropped in that case
    and normal processing carries on)."""
    items = pending.get("options") or []
    if not items or _is_stale(pending.get("created_at")):
        crud.clear_pending_selection(db, user_id)
        return None

    # A message with a number in it is a new transaction ("tea 20"), never
    # an answer to "which category?" - drop the question and let the normal
    # pipeline handle it.
    if any(ch.isdigit() for ch in message):
        crud.clear_pending_selection(db, user_id)
        return None

    current, rest = items[0], items[1:]
    term = current["term"]
    normalized = " ".join(glossary.tokenize(message))

    if any(phrase in normalized for phrase in _SKIP_PHRASES):
        return _finish(db, user_id, rest, f"No problem, I'll leave \"{term}\" as Other.")

    category = resolve_category_reply(message)
    if category is None:
        if not _looks_like_answer(message):
            crud.clear_pending_selection(db, user_id)
            return None
        current["attempts"] = int(current.get("attempts", 0)) + 1
        if current["attempts"] >= MAX_ATTEMPTS:
            return _finish(
                db, user_id, rest,
                f"I couldn't tell which category you meant, so \"{term}\" stays under Other. "
                f"You can change it from your transactions list any time.",
            )
        crud.set_pending_selection(db, user_id, PENDING_KIND, [current] + rest)
        return {
            "intent": "transaction",
            "reply": f"I didn't catch that. Which category is \"{term}\"? {_category_choices()}.",
            "data": None, "needs_confirmation": False, "candidates": None,
        }

    moved_amounts: list[float] = []
    for txn_id in current.get("txn_ids", []):
        row = crud.update_expense(db, user_id, txn_id, category=category)
        if row:
            moved_amounts.append(row.amount)
    crud.set_user_glossary_term(db, user_id, "expense", term, category)

    lead = f"Done, \"{term}\" goes under {category} from now on"
    if len(moved_amounts) == 1:
        lead += f", and I moved that {currency_service.format_amount(moved_amounts[0], currency)} entry there."
    elif moved_amounts:
        lead += f", and I moved those {len(moved_amounts)} entries there."
    else:
        lead += "."
    result = _finish(db, user_id, rest, lead)
    result["data"] = {"term": term, "category": category}
    return result
