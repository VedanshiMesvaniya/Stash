"""
database.py
Sets up the SQLAlchemy engine, session factory, and declarative base.

Production target is Postgres (Neon free tier) via DATABASE_URL. If
DATABASE_URL isn't set, falls back to a local SQLite file so you can still
run this on your laptop without Postgres installed. No balance is ever
stored; it is always derived from SUM(income) - SUM(expense) to avoid drift.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_SQLITE = not DATABASE_URL

if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'finance.db')}"

# Some hosts (Neon, Render, Heroku-style) hand out "postgres://" URLs but
# SQLAlchemy's psycopg2 dialect wants "postgresql://". Normalize it.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if IS_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
    )


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, connection_record):
    if "sqlite3" not in type(dbapi_connection).__module__:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and ensures it closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call once at app startup."""
    from . import models  # noqa: F401 ensures models are registered on Base
    from . import migrations

    migrations.run_migrations()
