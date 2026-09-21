"""
engine.py
Loads the JSON product glossary (app/glossary/data/{expense,income}/*.json)
and answers one question: "given this transaction description, which
Stash category does the item belong to?"

Why this exists: the LLM sometimes shrugs and answers "Other" for an
everyday item it doesn't recognise (e.g. "Dahi" -> Other). A deterministic
glossary fixes that class of miss, is the same answer every time, and can
be grown by editing JSON - no prompt tuning, no redeploy of a model.

Matching rules (kept deliberately simple and explainable):
  * Text is lower-cased, accents stripped, punctuation dropped and split
    into whole-word tokens. A term matches only on token boundaries, so
    "tea" never fires inside "steam" and "gas" never fires inside "vegas".
  * Leftmost-longest: a multi-word entry ("milk tea") beats the single
    words inside it ("milk").
  * The longest match wins. If two DIFFERENT categories tie for longest
    (e.g. "apple airpods" -> Groceries vs Shopping) the glossary refuses to
    guess and reports the tie, so the caller can fall back to the LLM.
  * Plural / singular forms of a term's last word are generated
    automatically ("biscuit" <-> "biscuits"); an explicit entry always beats
    a generated one.
  * Devanagari / Gujarati script terms work: tokenisation keeps combining
    marks (matras) attached to their letters.

The module has no DB or LLM dependency, so it is cheap to call and safe to
use from anywhere (extractor, services, scripts, tests).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
TXN_TYPES = ("expense", "income")

_COMBINING_LATIN = re.compile("[\u0300-\u036f]")


# --------------------------------------------------------------------------
# Tokenisation
# --------------------------------------------------------------------------

def tokenize(text: str | None) -> list[str]:
    """Lower-case, strip Latin accents, drop punctuation, split into words.
    Letters, combining marks and digits are kept (so Devanagari/Gujarati
    words stay in one piece); apostrophes are removed rather than split, so
    "domino's" -> "dominos"."""
    if not text:
        return []
    text = unicodedata.normalize("NFKD", str(text).casefold())
    text = _COMBINING_LATIN.sub("", text)
    tokens: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch in ("'", "\u2019", "`"):
            continue
        if unicodedata.category(ch)[0] in ("L", "M", "N"):
            current.append(ch)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def normalize_term(term: str | None) -> str:
    return " ".join(tokenize(term))


def _last_word_variants(word: str) -> set[str]:
    """Plural/singular forms of a single (ASCII) word. Generated variants
    only ever fill gaps - explicit glossary entries always win."""
    out: set[str] = set()
    if not word.isascii() or word.isdigit() or len(word) < 3:
        return out
    if word.endswith("y") and len(word) > 3 and word[-2] not in "aeiou":
        out.add(word[:-1] + "ies")
    elif word.endswith(("x", "z", "ch", "sh", "ss")) or word in ("gas", "bus"):
        out.add(word + "es")
    elif word.endswith("s"):
        pass  # already plural ("chips") - only the singular below is useful
    elif word.endswith("o"):
        out.update((word + "s", word + "es"))  # mango(s/es), tomato(s/es)
    else:
        out.add(word + "s")
    if word.endswith("oes") and len(word) > 5:
        out.add(word[:-2])  # tomatoes -> tomato (but not shoes -> "sho")
    if word.endswith("ies") and len(word) > 4:
        out.add(word[:-3] + "y")
    if word.endswith("es") and len(word) > 4 and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        out.add(word[:-2])  # boxes -> box, glasses -> glass
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        out.add(word[:-1])
    return out


# --------------------------------------------------------------------------
# Index + resolution
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    category: str
    term: str
    group: str | None = None
    generated: bool = False


@dataclass(frozen=True)
class Resolution:
    """Result of a lookup. `category` is None when the best matches tie
    across different categories - `ambiguous` then lists the tied ones."""
    category: str | None
    term: str | None = None
    group: str | None = None
    strength: int = 0
    ambiguous: tuple[str, ...] = ()


@dataclass
class Index:
    entries: dict[str, Entry] = field(default_factory=dict)
    max_len: int = 1
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)  # (term, kept, dropped)
    _pending: list[tuple[str, str, str | None]] = field(default_factory=list, repr=False)

    def add(self, term: str, category: str, group: str | None = None) -> None:
        tokens = tokenize(term)
        if not tokens or not category:
            return
        key = " ".join(tokens)
        existing = self.entries.get(key)
        if existing is not None and not existing.generated:
            if existing.category != category:
                self.conflicts.append((key, existing.category, category))
            return
        self.entries[key] = Entry(category=category, term=key, group=group)
        self.max_len = max(self.max_len, len(tokens))
        self._pending.append((key, category, group))

    def finalize(self) -> "Index":
        """Adds generated plural/singular variants of every explicit entry's
        last word, without ever overwriting an explicit entry."""
        for key, category, group in self._pending:
            tokens = key.split(" ")
            for variant in _last_word_variants(tokens[-1]):
                vkey = " ".join(tokens[:-1] + [variant])
                if vkey not in self.entries:
                    self.entries[vkey] = Entry(category=category, term=key, group=group, generated=True)
        self._pending = []
        return self


def resolve(text: str | None, index: Index) -> Resolution | None:
    """Longest-match lookup of `text` against `index`. Returns None when
    nothing matched at all."""
    tokens = tokenize(text)
    if not tokens or not index.entries:
        return None

    hits: list[tuple[int, Entry]] = []
    i = 0
    while i < len(tokens):
        for length in range(min(index.max_len, len(tokens) - i), 0, -1):
            entry = index.entries.get(" ".join(tokens[i:i + length]))
            if entry is not None:
                hits.append((length, entry))
                i += length
                break
        else:
            i += 1

    if not hits:
        return None

    best = max(length for length, _ in hits)
    by_category: dict[str, Entry] = {}
    for length, entry in hits:
        if length == best:
            by_category.setdefault(entry.category, entry)

    if len(by_category) == 1:
        category, entry = next(iter(by_category.items()))
        return Resolution(category=category, term=entry.term, group=entry.group, strength=best)
    return Resolution(category=None, strength=best, ambiguous=tuple(sorted(by_category)))


# --------------------------------------------------------------------------
# Loading the JSON files
# --------------------------------------------------------------------------

class Glossary:
    def __init__(self) -> None:
        self.indexes: dict[str, Index] = {t: Index() for t in TXN_TYPES}
        self.files_loaded = 0
        self.errors: list[str] = []

    def load(self, data_dir: Path = DATA_DIR) -> "Glossary":
        for txn_type in TXN_TYPES:
            folder = data_dir / txn_type
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                try:
                    self._load_file(path, txn_type)
                except Exception as exc:  # noqa: BLE001 - a bad data file must never take chat down
                    message = f"{path.name}: {exc}"
                    self.errors.append(message)
                    logger.error("Glossary file skipped (%s)", message)
        for index in self.indexes.values():
            index.finalize()
            for term, kept, dropped in index.conflicts:
                logger.warning("Glossary conflict for %r: kept %s, ignored %s", term, kept, dropped)
        return self

    def _load_file(self, path: Path, txn_type: str) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        category = str(payload["category"]).strip()
        declared_type = payload.get("type", txn_type)
        if declared_type != txn_type:
            raise ValueError(f"declares type {declared_type!r} but lives in {txn_type}/")
        groups = payload.get("groups", {})
        if not isinstance(groups, dict):
            raise ValueError("'groups' must be an object of {group_name: [terms]}")
        index = self.indexes[txn_type]
        for group_name, terms in groups.items():
            if not isinstance(terms, list):
                raise ValueError(f"group {group_name!r} must be a list of strings")
            for term in terms:
                index.add(str(term), category, group_name)
        self.files_loaded += 1


@lru_cache(maxsize=1)
def get_glossary() -> Glossary:
    return Glossary().load()


def reload_glossary() -> Glossary:
    """Drops the cache and re-reads the JSON files (used by tests/scripts)."""
    get_glossary.cache_clear()
    return get_glossary()


def lookup(text: str | None, txn_type: str = "expense") -> Resolution | None:
    """Category for `text` from the built-in glossary, or None when nothing
    matched. Never raises - a glossary problem must degrade to "no opinion",
    not break the chat pipeline."""
    try:
        index = get_glossary().indexes.get(txn_type)
        if index is None:
            return None
        return resolve(text, index)
    except Exception:  # noqa: BLE001
        logger.exception("Glossary lookup failed")
        return None


def stats() -> dict:
    glossary = get_glossary()
    result: dict = {"files": glossary.files_loaded, "errors": list(glossary.errors), "types": {}}
    for txn_type, index in glossary.indexes.items():
        per_category: dict[str, int] = {}
        for entry in index.entries.values():
            if not entry.generated:
                per_category[entry.category] = per_category.get(entry.category, 0) + 1
        result["types"][txn_type] = {"terms": sum(per_category.values()), "by_category": dict(sorted(per_category.items()))}
    return result


# --------------------------------------------------------------------------
# Picking the "item" out of a free-text description (for the ask-the-user flow)
# --------------------------------------------------------------------------

_FILLER = {
    # verbs / connectors people wrap an item in
    "spent", "spend", "spending", "paid", "pay", "paying", "bought", "buy", "buying", "purchase", "purchased",
    "got", "get", "took", "take", "gave", "give", "ordered", "order", "had", "have", "did", "was", "were",
    "is", "am", "are", "be", "been", "i", "we", "me", "my", "our", "us", "just", "only", "also", "some",
    "on", "for", "at", "in", "the", "a", "an", "of", "to", "from", "with", "and", "or", "about", "around",
    "worth", "into", "by", "as", "it", "its", "that", "this", "these", "those", "there", "then",
    # money / payment words
    "rs", "rupee", "rupees", "rupaye", "rupay", "inr", "amount", "cash", "online", "upi", "gpay", "phonepe",
    "paytm", "card", "bill", "payment", "paid",
    # time words
    "today", "yesterday", "tomorrow", "tonight", "morning", "afternoon", "evening", "night", "ago", "day",
    "days", "week", "weeks", "last", "this", "next", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "kal", "aaj", "parso",
}

# Words that mean "no real item was named" - never worth asking about.
_NON_ITEM = {
    "expense", "expenses", "misc", "miscellaneous", "other", "others", "stuff", "things", "thing", "something",
    "item", "items", "money", "transaction", "transactions", "balance", "opening", "starting", "withdrawal",
    "withdraw", "withdrew", "transfer", "transferred", "adjustment", "entry", "entries", "spending", "unknown",
    "salary", "income", "refund", "cashback",
}

MAX_TERM_WORDS = 3


def extract_unknown_term(description: str | None) -> str | None:
    """Best-effort: the 1-3 word item/merchant name inside a description
    like "Spent on kalakand" -> "kalakand". Returns None when nothing
    usable is left (an empty/generic description, or a whole sentence) -
    in that case Stash should not bother the user with a question."""
    tokens = tokenize(description)
    kept = [t for t in tokens if t not in _FILLER and not t.isdigit() and len(t) > 1]
    if not kept or len(kept) > MAX_TERM_WORDS:
        return None
    if any(t in _NON_ITEM for t in kept):
        return None
    return " ".join(kept)
