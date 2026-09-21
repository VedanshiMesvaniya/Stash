"""
Validates the JSON product glossary (app/glossary/data/) - run locally or
in CI before committing changes to the glossary:

    python3 scripts/validate_glossary.py

Fails (exit 1) when a file is malformed, names a category the app doesn't
have, lives in the wrong type folder, or when the same term is listed under
two different categories (which would make the answer depend on load order).
Prints per-category term counts on success.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.prompts import CATEGORIES_EXPENSE, CATEGORIES_INCOME  # noqa: E402
from app.glossary import engine  # noqa: E402

VALID = {"expense": set(CATEGORIES_EXPENSE), "income": set(CATEGORIES_INCOME)}


def main() -> int:
    problems: list[str] = []

    for txn_type in engine.TXN_TYPES:
        folder = engine.DATA_DIR / txn_type
        files = sorted(folder.glob("*.json")) if folder.is_dir() else []
        if not files:
            problems.append(f"{txn_type}/: no glossary files found")
        for path in files:
            label = f"{txn_type}/{path.name}"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{label}: not valid JSON ({exc})")
                continue
            category = payload.get("category")
            if category not in VALID[txn_type]:
                problems.append(f"{label}: category {category!r} is not one of {sorted(VALID[txn_type])}")
            if payload.get("type", txn_type) != txn_type:
                problems.append(f"{label}: 'type' is {payload.get('type')!r} but the file is in {txn_type}/")
            groups = payload.get("groups")
            if not isinstance(groups, dict) or not groups:
                problems.append(f"{label}: 'groups' must be a non-empty object")
                continue
            for group, terms in groups.items():
                if not isinstance(terms, list):
                    problems.append(f"{label}: group {group!r} must be a list")
                    continue
                for term in terms:
                    if not isinstance(term, str) or not engine.normalize_term(term):
                        problems.append(f"{label}: group {group!r} has an unusable term {term!r}")

    glossary = engine.reload_glossary()
    problems.extend(f"loader: {err}" for err in glossary.errors)
    for txn_type, index in glossary.indexes.items():
        for term, kept, dropped in index.conflicts:
            problems.append(f"{txn_type}: {term!r} is listed under both {kept} and {dropped}")

    if problems:
        print("Glossary validation FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    stats = engine.stats()
    for txn_type, info in stats["types"].items():
        print(f"{txn_type}: {info['terms']} terms")
        for category, count in info["by_category"].items():
            print(f"    {category}: {count}")
    print("Glossary OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
