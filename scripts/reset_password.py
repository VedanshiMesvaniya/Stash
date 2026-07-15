"""
reset_password.py
CLI-only password reset - this is the replacement for the old hardcoded
recovery-password backdoor. Requires shell/filesystem access to the server
(Render shell, or SSH on a VPS), NOT a network-facing endpoint, so it can't
be brute-forced or discovered by reading the repo.

Usage:
    python -m scripts.reset_password <username> <new_password>
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import SessionLocal
from app.database import crud
from app.auth.password import hash_password


def main():
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.reset_password <username> <new_password>")
        sys.exit(1)

    username, new_password = sys.argv[1], sys.argv[2]
    db = SessionLocal()
    try:
        user = crud.get_user_by_username(db, username)
        if not user:
            print(f"No user found with username '{username}'.")
            sys.exit(1)
        user.password_hash = hash_password(new_password)
        db.commit()
        print(f"Password updated for '{username}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
