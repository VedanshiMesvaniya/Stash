"""
models.py
ORM models for Stash. Note deliberately: there is NO Balance table/column
anywhere. Balance is always computed at query time as
SUM(Income.amount) - SUM(Expense.amount) to prevent drift between a stored
value and the actual transaction history.

Multi-user note: every transaction-bearing table carries a user_id FK so
each family member's data is fully isolated. Category stays global/shared
since categories aren't sensitive and there's no benefit to duplicating them
per user.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, Date, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    """A Stash account. Accounts are created statically via seed.py (see
    that file to change usernames/passwords) rather than through open
    self-signup, matching the 'give them the login, they can't self-register'
    requirement."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=True)

    monthly_alert_amount = Column(Float, nullable=True, default=1000.0)
    salary_day = Column(Integer, nullable=True, default=1)
    currency = Column(String, default="INR")
    theme = Column(String, default="obsidian")
    lock_enabled = Column(Boolean, nullable=False, default=False)
    lock_pin_hash = Column(String, nullable=True)
    biometric_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Income(Base):
    __tablename__ = "income"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    source = Column(String, nullable=False, default="Other")
    description = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    month = Column(Integer, nullable=False)  # 1-12, denormalized for fast report queries
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Expense(Base):
    __tablename__ = "expense"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False, default="Other")
    description = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "type", name="uq_category_name_type"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # "income" or "expense"


class ChatMessage(Base):
    """Stores chat history so the timeline/dashboard can show the conversation
    and so Stash has short-term memory of recent exchanges."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    category_or_source = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)  # income or expense
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    cadence = Column(String, nullable=False, default="monthly")  # monthly, quarterly, custom
    start_date = Column(Date, nullable=False)
    next_due_date = Column(Date, nullable=False)
    interval_months = Column(Integer, nullable=False, default=1)
    total_cycles = Column(Integer, nullable=True)
    cycles_completed = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RecurringPosting(Base):
    __tablename__ = "recurring_postings"
    __table_args__ = (UniqueConstraint("recurring_id", "posted_for_date", name="uq_recurring_posting_once"),)

    id = Column(Integer, primary_key=True, index=True)
    recurring_id = Column(Integer, ForeignKey("recurring_transactions.id"), nullable=False, index=True)
    posted_for_date = Column(Date, nullable=False)
    transaction_type = Column(String, nullable=False)
    transaction_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PendingEntry(Base):
    """Queue for chat messages that couldn't be processed immediately because
    both LLM providers (Groq, then OpenRouter) were unavailable/rate-limited.
    A background job (see main.py) retries these every few minutes so the
    user's raw message is never lost, even across app restarts - that's the
    whole point of this being a DB table and not an in-memory cache."""
    __tablename__ = "pending_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    raw_message = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | processed | failed
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
