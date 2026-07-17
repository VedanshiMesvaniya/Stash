"""
manage_users.py
Console helper for adding or deleting Stash users.

Usage:
    python -m scripts.manage_users add <username> <password> [display_name]
    python -m scripts.manage_users delete <username>
    python -m scripts.manage_users list

The command updates the database and also keeps the gitignored private
account file in sync when it exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.database.database import SessionLocal  # noqa: E402
from app.database import crud, models  # noqa: E402
from app.auth.password import hash_password  # noqa: E402
from app.database.seed import upsert_private_account, delete_private_account  # noqa: E402


def _display_name(username: str, provided: str | None) -> str:
    if provided:
        return provided.strip()
    return username.strip().replace("_", " ").title()


def _delete_user_data(db, user_id: int) -> dict[str, int]:
    recurring_ids = [
        row.id for row in db.query(models.RecurringTransaction.id).filter(models.RecurringTransaction.user_id == user_id).all()
    ]

    counts = {
        "chat_messages": db.query(models.ChatMessage).filter(models.ChatMessage.user_id == user_id).delete(synchronize_session=False),
        "pending_entries": db.query(models.PendingEntry).filter(models.PendingEntry.user_id == user_id).delete(synchronize_session=False),
        "income": db.query(models.Income).filter(models.Income.user_id == user_id).delete(synchronize_session=False),
        "expense": db.query(models.Expense).filter(models.Expense.user_id == user_id).delete(synchronize_session=False),
        "recurring_postings": 0,
        "recurring_transactions": 0,
    }

    if recurring_ids:
        counts["recurring_postings"] = db.query(models.RecurringPosting).filter(
            models.RecurringPosting.recurring_id.in_(recurring_ids)
        ).delete(synchronize_session=False)

    counts["recurring_transactions"] = db.query(models.RecurringTransaction).filter(
        models.RecurringTransaction.user_id == user_id
    ).delete(synchronize_session=False)

    db.commit()
    return counts


def list_users() -> int:
    db = SessionLocal()
    try:
        rows = db.query(models.User).order_by(models.User.username.asc()).all()
        if not rows:
            print("No users found.")
            return 0
        for row in rows:
            label = row.display_name or "-"
            print(f"{row.username}\t{label}\tuser_id={row.id}")
        return 0
    finally:
        db.close()


def add_user(username: str, password: str, display_name: str | None = None) -> int:
    username = username.strip()
    if not username:
        print("Username cannot be empty.")
        return 1
    if not password:
        print("Password cannot be empty.")
        return 1

    db = SessionLocal()
    try:
        existing = crud.get_user_by_username(db, username)
        if existing:
            print(f"User '{username}' already exists.")
            return 1

        user = models.User(
            username=username,
            password_hash=hash_password(password),
            display_name=_display_name(username, display_name),
            currency="INR",
            theme="obsidian",
            monthly_alert_amount=1000.0,
            salary_day=1,
        )
        db.add(user)
        db.commit()
        print(f"Added user '{username}'.")

        if upsert_private_account(username, password, user.display_name or username):
            print("Private account file updated.")
        else:
            print("Private account file was not updated.")
        return 0
    finally:
        db.close()


def delete_user(username: str) -> int:
    username = username.strip()
    if not username:
        print("Username cannot be empty.")
        return 1

    db = SessionLocal()
    try:
        user = crud.get_user_by_username(db, username)
        if not user:
            print(f"User '{username}' not found.")
            return 1

        counts = _delete_user_data(db, user.id)
        db.delete(user)
        db.commit()

        print(f"Deleted user '{username}'.")
        print(
            "Removed rows: "
            f"income={counts['income']}, expense={counts['expense']}, "
            f"chat_messages={counts['chat_messages']}, recurring_transactions={counts['recurring_transactions']}, "
            f"recurring_postings={counts['recurring_postings']}, pending_entries={counts['pending_entries']}"
        )

        if delete_private_account(username):
            print("Private account file updated.")
        return 0
    finally:
        db.close()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    command = sys.argv[1].lower()
    if command == "list":
        return list_users()
    if command == "add":
        if len(sys.argv) not in (4, 5):
            print("Usage: python -m scripts.manage_users add <username> <password> [display_name]")
            return 1
        username = sys.argv[2]
        password = sys.argv[3]
        display_name = sys.argv[4] if len(sys.argv) == 5 else None
        return add_user(username, password, display_name)
    if command == "delete":
        if len(sys.argv) != 3:
            print("Usage: python -m scripts.manage_users delete <username>")
            return 1
        return delete_user(sys.argv[2])

    print(f"Unknown command '{command}'.")
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
