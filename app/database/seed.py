"""
seed.py
Seeds default categories AND the 5 static family accounts. Safe to run
multiple times (checks for existing rows before inserting).

>>> TO CHANGE USERNAMES/PASSWORDS: edit FAMILY_ACCOUNTS below, then restart
the app once. Existing users are left alone (this only creates missing
ones) - so if you change a password here after the account already exists,
it will NOT update the live password. Use scripts/reset_password.py for that.

These are intentionally simple, easy-to-type passwords since this is a
private family app, not a bank. Still: don't leave this file in a PUBLIC
GitHub repo with real passwords in it - keep the repo private, or move
these into environment variables before deploying if you're worried.

If you change a live password through the app or the CLI reset tool, the
helper below can rewrite the matching FAMILY_ACCOUNTS entry so this file
stays in sync for tracking.
"""

import json
import re
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

# username, password, display_name - edit freely.
FAMILY_ACCOUNTS = [
    ("vedu",   "vedu@2026",   "Vedu"),
    ("mummy",  "mummy@2026",  "Mummy"),
    ("papa",   "papa@2026",   "Papa"),
    ("family1", "family1@2026", "Family Member 1"),
    ("family2", "family2@2026", "Family Member 2"),
]


def update_family_account_password(username: str, new_password: str, new_username: str | None = None) -> bool:
    """Rewrite the matching FAMILY_ACCOUNTS row in this source file.

    This keeps the seed list aligned with a live password change so the
    account detail remains visible in one place for later review.
    """
    seed_path = Path(__file__).resolve()
    lines = seed_path.read_text(encoding="utf-8").splitlines(keepends=True)
    pattern = re.compile(
        r'^(?P<indent>\s*)\("(?P<username>(?:\\.|[^"])*)",\s*"(?P<password>(?:\\.|[^"])*)",\s*"(?P<display_name>(?:\\.|[^"])*)"\),?(?P<suffix>\s*)$'
    )

    for index, line in enumerate(lines):
        match = pattern.match(line.rstrip("\n"))
        if not match or match.group("username") != username:
            continue
        indent = match.group("indent")
        next_username = new_username or match.group("username")
        display_name = match.group("display_name")
        lines[index] = f'{indent}({json.dumps(next_username)}, {json.dumps(new_password)}, {json.dumps(display_name)}),\n'
        seed_path.write_text("".join(lines), encoding="utf-8")
        return True

    return False


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
    for username, password, display_name in FAMILY_ACCOUNTS:
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
