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
"""

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
