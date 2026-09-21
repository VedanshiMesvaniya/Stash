"""
Product / merchant glossary: a data-driven "what category is this item?"
lookup that runs before (and independently of) the LLM's own guess.

See app/glossary/engine.py for the matching rules and
app/glossary/data/README.md for how to grow the JSON files.
"""

from .engine import (  # noqa: F401
    Index,
    Resolution,
    extract_unknown_term,
    get_glossary,
    lookup,
    normalize_term,
    resolve,
    stats,
    tokenize,
)
