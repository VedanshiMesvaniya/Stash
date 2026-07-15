"""
backup.py
Backup/restore via straight SQLite file copy - this only works when running
on local SQLite (no DATABASE_URL set). Once you're on Neon Postgres for the
real deployment, use Neon's own point-in-time restore / branching instead of
this: https://neon.tech/docs/introduction/branching - a local file copy of a
remote Postgres DB isn't meaningful anyway. This module raises a clear error
in Postgres mode rather than silently doing nothing.
"""

import os
import shutil
from datetime import datetime

from app.database.database import IS_SQLITE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "finance.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")


def _require_sqlite():
    if not IS_SQLITE:
        raise RuntimeError(
            "File-copy backup only works with local SQLite. You're running on Postgres "
            "(Neon) - use Neon's branching/point-in-time restore instead: "
            "https://neon.tech/docs/introduction/branching"
        )


def create_backup() -> str:
    _require_sqlite()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"finance_backup_{timestamp}.db")
    shutil.copy2(DB_PATH, dest)
    return dest


def list_backups() -> list[str]:
    if not IS_SQLITE or not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
        reverse=True,
    )


def restore_backup(filename: str) -> None:
    _require_sqlite()
    src = os.path.join(BACKUP_DIR, filename)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Backup {filename} not found.")
    # Safety net: back up the current DB before overwriting it.
    create_backup()
    shutil.copy2(src, DB_PATH)
