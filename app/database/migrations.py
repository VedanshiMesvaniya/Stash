"""
migrations.py
Tiny schema upgrader for in-place schema changes without Alembic. Works for
both SQLite and Postgres (Neon) since it only uses SQLAlchemy's generic
inspector + a plain ALTER TABLE, which both dialects support for simple
column adds.
"""

from sqlalchemy import inspect, text

from .database import engine, Base


def _table_columns(connection, table_name: str) -> set[str]:
    inspector = inspect(connection)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(connection, table_name: str, column_name: str, ddl: str):
    if column_name in _table_columns(connection, table_name):
        return
    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def run_migrations():
    from . import models  # noqa: F401 ensures models are registered on Base

    # Create any new tables (users, pending_entries, user_id-bearing tables
    # for a fresh DB). This does NOT retrofit user_id onto rows from the old
    # single-user schema - if you're upgrading an existing local SQLite DB
    # from before multi-user support, wipe data/finance.db and start fresh,
    # or you'll get NOT NULL errors on user_id. Neon (a fresh DB) doesn't
    # have this problem at all.
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        _add_column_if_missing(connection, "users", "display_name", "display_name VARCHAR")
        _add_column_if_missing(connection, "income", "payment_method", "payment_method VARCHAR")
        _add_column_if_missing(connection, "expense", "payment_method", "payment_method VARCHAR")
