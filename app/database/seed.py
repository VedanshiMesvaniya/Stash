"""Seed default categories plus login accounts.

Public demo credentials stay in this file so the shared demo can be used
without extra setup. Personal accounts belong in the gitignored
`private_accounts.py` file next to this module.
"""

import importlib.util
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.auth.password import hash_password
from . import models

DEFAULT_EXPENSE_CATEGORIES = [
    "Snacks", "Tea", "Food", "Groceries", "Petrol", "Shopping", "Bills",
    "Travel", "Entertainment", "Medical", "Education", "Investment", "Other",
]

DEFAULT_INCOME_CATEGORIES = [
    "Salary", "Freelance", "Gift", "Refund", "Other",
]

# username, password, display_name - public demo account only.
PUBLIC_ACCOUNTS = [
    ("guest", "12345", "Guest Demo"),
]

PRIVATE_ACCOUNTS_FILE = Path(__file__).with_name("private_accounts.py")


def _load_private_accounts() -> list[tuple[str, str, str]]:
    if not PRIVATE_ACCOUNTS_FILE.exists():
        return []

    spec = importlib.util.spec_from_file_location("app.database.private_accounts", PRIVATE_ACCOUNTS_FILE)
    if not spec or not spec.loader:
        return []

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    accounts = getattr(module, "PRIVATE_ACCOUNTS", [])
    normalized = []
    for entry in accounts:
        if isinstance(entry, (list, tuple)) and len(entry) == 3:
            normalized.append((str(entry[0]), str(entry[1]), str(entry[2])))
    return normalized


def _write_private_accounts(rows: list[tuple[str, str, str]]) -> None:
    PRIVATE_ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = ["PRIVATE_ACCOUNTS = [\n"]
    for username, password, display_name in rows:
        content.append(f"    ({json.dumps(username)}, {json.dumps(password)}, {json.dumps(display_name)}),\n")
    content.append("]\n")
    PRIVATE_ACCOUNTS_FILE.write_text("".join(content), encoding="utf-8")


def upsert_private_account(username: str, password: str, display_name: str) -> bool:
    rows = _load_private_accounts()
    normalized_username = username.strip()
    if not normalized_username:
        return False
    updated = False
    for index, row in enumerate(rows):
        if row[0].lower() == normalized_username.lower():
            rows[index] = (normalized_username, password, display_name)
            updated = True
            break
    if not updated:
        rows.append((normalized_username, password, display_name))
    _write_private_accounts(rows)
    return True


def delete_private_account(username: str) -> bool:
    if not PRIVATE_ACCOUNTS_FILE.exists():
        return False
    rows = _load_private_accounts()
    filtered = [row for row in rows if row[0].lower() != username.strip().lower()]
    if len(filtered) == len(rows):
        return False
    _write_private_accounts(filtered)
    return True


def update_family_account_password(username: str, new_password: str, new_username: str | None = None) -> bool:
    """Keep the gitignored private account list in sync with a password change."""
    rows = _load_private_accounts()
    if not rows:
        return False

    normalized_username = username.strip().lower()
    updated = False
    for index, row in enumerate(rows):
        if row[0].lower() != normalized_username:
            continue
        rows[index] = (new_username or row[0], new_password, row[2])
        updated = True
        break

    if not updated:
        return False

    _write_private_accounts(rows)
    return True


def seed_categories(db: Session):
    # If categories already exist, don't seed again to avoid duplicates
    count = db.query(models.Category).count()
    if count > 0:
        return
    
    new_rows = []
    for name in DEFAULT_EXPENSE_CATEGORIES:
        new_rows.append(models.Category(name=name, type="expense"))
    for name in DEFAULT_INCOME_CATEGORIES:
        new_rows.append(models.Category(name=name, type="income"))
    
    db.add_all(new_rows)
    db.commit()


def seed_users(db: Session):
    existing_usernames = {u.username for u in db.query(models.User).all()}
    new_rows = []
    for username, password, display_name in [*PUBLIC_ACCOUNTS, *_load_private_accounts()]:
        if username in existing_usernames:
            continue
        new_rows.append(
            models.User(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name,
                currency="INR",
                theme="obsidian",
                monthly_alert_amount=1000.0,
                salary_day=1,
            )
        )
    if new_rows:
        db.add_all(new_rows)
        db.commit()
