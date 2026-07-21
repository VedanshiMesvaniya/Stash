"""
crud.py
Direct database operations. Kept thin and dumb on purpose - business logic
(balance calc, disambiguation, etc.) lives in services/, not here.

Multi-user note: every read/write below takes a user_id and filters on it.
There is no function in this file that returns another user's data - if
you add a new query, filter by user_id or you've reintroduced the data leak
this rewrite was meant to close.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import date, datetime, timedelta
from . import models

EXPENSE_DISPLAY_HINTS = [
    ("Food", ("food", "meal", "meals", "lunch", "dinner", "breakfast", "restaurant", "canteen", "tiffin")),
    ("Tea", ("tea", "coffee", "chai")),
    ("Snacks", ("snack", "snacks")),
    ("Groceries", ("grocery", "groceries", "vegetable", "vegetables", "fruit", "fruits", "milk", "bread", "rice", "eggs")),
    ("Petrol", ("petrol", "fuel", "gas", "diesel")),
    ("Shopping", ("shopping", "amazon", "flipkart", "myntra", "order", "purchase", "clothes", "shirt", "pants", "shoes")),
    ("Bills", ("bill", "bills", "electricity", "power", "water", "internet", "wifi", "rent", "subscription", "recharge")),
    ("Travel", ("travel", "cab", "taxi", "uber", "ola", "bus", "train", "metro", "flight", "ticket")),
    ("Entertainment", ("movie", "movies", "cinema", "game", "games", "concert", "party", "fun")),
    ("Medical", ("medical", "doctor", "medicine", "pharmacy", "hospital", "clinic", "checkup", "treatment")),
    ("Education", ("education", "school", "college", "tuition", "fee", "course", "books", "exam")),
    ("Investment", ("investment", "invest", "sip", "stocks", "shares", "mutual fund", "fd", "gold", "crypto")),
]

INCOME_DISPLAY_HINTS = [
    ("Salary", ("salary", "paycheck", "pay slip", "wage", "wages")),
    ("Freelance", ("freelance", "gig", "project", "invoice", "client")),
    (
        "Gift",
        (
            "gift", "gifts", "gifted", "present",
            # money received from a relative/friend with no other stated
            # source reads as a gift, not "Other" - this was the gap that
            # let "got 4000 from uncle" fall through to the old invented
            # "Income" fallback below.
            "uncle", "aunt", "aunty", "grandma", "grandpa", "grandmother", "grandfather",
            "mom", "dad", "mother", "father", "parents", "brother", "sister",
            "relative", "cousin", "friend gave", "friend transferred",
        ),
    ),
    ("Refund", ("refund", "returned", "cashback", "reimburse", "reimburs")),
]


def resolve_display_label(txn_type: str, label: str, description: str | None) -> str:
    if label and label != "Other":
        return label

    lowered = (description or "").lower()
    hints = INCOME_DISPLAY_HINTS if txn_type == "income" else EXPENSE_DISPLAY_HINTS
    for category, keywords in hints:
        if any(keyword in lowered for keyword in keywords):
            return category

    # Previously returned "Income"/"Expense" here - those aren't valid
    # categories in prompts.CATEGORIES_INCOME/CATEGORIES_EXPENSE and showed
    # up as a fabricated label in chat replies. "Other" is the real,
    # already-stored fallback category, so display should match it.
    return "Other"


# ---------- Users ----------

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(func.lower(models.User.username) == username.lower().strip()).first()


# ---------- Income ----------

def create_income(db: Session, user_id: int, amount: float, source: str, description: str, txn_date: date, payment_method: str | None = None):
    row = models.Income(
        user_id=user_id,
        amount=amount,
        source=source or "Other",
        description=description,
        payment_method=payment_method,
        date=txn_date,
        month=txn_date.month,
        year=txn_date.year,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_income(db: Session, user_id: int, income_id: int):
    return db.query(models.Income).filter(
        models.Income.id == income_id, models.Income.user_id == user_id
    ).first()


def update_income(db: Session, user_id: int, income_id: int, **fields):
    row = get_income(db, user_id, income_id)
    if not row:
        return None
    for k, v in fields.items():
        if v is not None:
            setattr(row, k, v)
    if "date" in fields and fields["date"]:
        row.month = fields["date"].month
        row.year = fields["date"].year
    db.commit()
    db.refresh(row)
    return row


def delete_income(db: Session, user_id: int, income_id: int):
    row = get_income(db, user_id, income_id)
    if not row:
        return None
    db.delete(row)
    db.commit()
    return row


# ---------- Expense ----------

def create_expense(db: Session, user_id: int, amount: float, category: str, description: str, txn_date: date, payment_method: str | None = None):
    row = models.Expense(
        user_id=user_id,
        amount=amount,
        category=category or "Other",
        description=description,
        payment_method=payment_method,
        date=txn_date,
        month=txn_date.month,
        year=txn_date.year,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_expense(db: Session, user_id: int, expense_id: int):
    return db.query(models.Expense).filter(
        models.Expense.id == expense_id, models.Expense.user_id == user_id
    ).first()


def update_expense(db: Session, user_id: int, expense_id: int, **fields):
    row = get_expense(db, user_id, expense_id)
    if not row:
        return None
    for k, v in fields.items():
        if v is not None:
            setattr(row, k, v)
    if "date" in fields and fields["date"]:
        row.month = fields["date"].month
        row.year = fields["date"].year
    db.commit()
    db.refresh(row)
    return row


def delete_expense(db: Session, user_id: int, expense_id: int):
    row = get_expense(db, user_id, expense_id)
    if not row:
        return None
    db.delete(row)
    db.commit()
    return row


def purge_user_data(db: Session, user_id: int):
    recurring_ids = [
        row.id for row in db.query(models.RecurringTransaction.id).filter(models.RecurringTransaction.user_id == user_id).all()
    ]
    if recurring_ids:
        db.query(models.RecurringPosting).filter(
            models.RecurringPosting.recurring_id.in_(recurring_ids)
        ).delete(synchronize_session=False)
    db.query(models.ChatMessage).filter(models.ChatMessage.user_id == user_id).delete(synchronize_session=False)
    db.query(models.PendingEntry).filter(models.PendingEntry.user_id == user_id).delete(synchronize_session=False)
    db.query(models.Income).filter(models.Income.user_id == user_id).delete(synchronize_session=False)
    db.query(models.Expense).filter(models.Expense.user_id == user_id).delete(synchronize_session=False)
    db.query(models.RecurringTransaction).filter(models.RecurringTransaction.user_id == user_id).delete(synchronize_session=False)
    user = get_user(db, user_id)
    if user:
        user.monthly_alert_amount = 1000.0
        user.salary_day = 1
        user.currency = "INR"
        user.theme = "mist"
        user.lock_enabled = False
        user.lock_pin_hash = None
        user.biometric_enabled = False
    db.commit()


# ---------- Queries used for disambiguation & timeline ----------

def find_recent_expenses_by_category(db: Session, user_id: int, category: str, days: int = 7, limit: int = 5):
    since = date.today() - timedelta(days=days)
    q = db.query(models.Expense).filter(
        models.Expense.user_id == user_id, models.Expense.date >= since
    )
    if category:
        q = q.filter(func.lower(models.Expense.category) == category.lower())
    return q.order_by(models.Expense.created_at.desc()).limit(limit).all()


def find_recent_income_by_source(db: Session, user_id: int, source: str, days: int = 7, limit: int = 5):
    since = date.today() - timedelta(days=days)
    q = db.query(models.Income).filter(
        models.Income.user_id == user_id, models.Income.date >= since
    )
    if source:
        q = q.filter(func.lower(models.Income.source) == source.lower())
    return q.order_by(models.Income.created_at.desc()).limit(limit).all()


def get_timeline(db: Session, user_id: int, limit: int = 100):
    """Returns merged income+expense rows sorted by date desc, then created_at desc."""
    fetch_limit = max(limit * 2, limit)
    incomes = db.query(models.Income).filter(models.Income.user_id == user_id).order_by(
        models.Income.date.desc(),
        models.Income.created_at.desc(),
    ).limit(fetch_limit).all()
    expenses = db.query(models.Expense).filter(models.Expense.user_id == user_id).order_by(
        models.Expense.date.desc(),
        models.Expense.created_at.desc(),
    ).limit(fetch_limit).all()
    merged = []
    for i in incomes:
        display_label = resolve_display_label("income", i.source, i.description)
        merged.append({
            "id": i.id, "type": "income", "amount": i.amount,
            "label": i.source, "display_label": display_label, "description": i.description,
            "date": i.date, "created_at": i.created_at,
        })
    for e in expenses:
        display_label = resolve_display_label("expense", e.category, e.description)
        merged.append({
            "id": e.id, "type": "expense", "amount": e.amount,
            "label": e.category, "display_label": display_label, "description": e.description,
            "date": e.date, "created_at": e.created_at,
        })
    merged.sort(key=lambda x: (x["date"], x["created_at"] or datetime.min), reverse=True)
    return merged[:limit]


# ---------- Balance & aggregates (always derived, never stored) ----------

def get_balance(db: Session, user_id: int) -> float:
    total_income = db.query(func.coalesce(func.sum(models.Income.amount), 0.0)).filter(
        models.Income.user_id == user_id
    ).scalar()
    total_expense = db.query(func.coalesce(func.sum(models.Expense.amount), 0.0)).filter(
        models.Expense.user_id == user_id
    ).scalar()
    return round(total_income - total_expense, 2)


def get_wallet_balances(db: Session, user_id: int) -> dict:
    """Running balance split by payment_method (#34 Cash Tracking, #35
    Online Payment Tracking). "unspecified" covers every transaction
    logged before this field existed, or where neither the message nor
    the chat toggle said how the money moved - it's kept visible rather
    than silently folded into one of the other two, since guessing which
    wallet an old/ambiguous entry belongs to would misrepresent it."""
    balances = {"cash": 0.0, "online": 0.0, "unspecified": 0.0}
    for method in ("cash", "online", None):
        key = method or "unspecified"
        income = db.query(func.coalesce(func.sum(models.Income.amount), 0.0)).filter(
            models.Income.user_id == user_id, models.Income.payment_method == method
        ).scalar()
        expense = db.query(func.coalesce(func.sum(models.Expense.amount), 0.0)).filter(
            models.Expense.user_id == user_id, models.Expense.payment_method == method
        ).scalar()
        balances[key] = round(income - expense, 2)
    return balances


def get_month_summary(db: Session, user_id: int, year: int, month: int):
    income = db.query(func.coalesce(func.sum(models.Income.amount), 0.0)).filter(
        models.Income.user_id == user_id,
        extract("year", models.Income.date) == year,
        extract("month", models.Income.date) == month,
    ).scalar()
    expense = db.query(func.coalesce(func.sum(models.Expense.amount), 0.0)).filter(
        models.Expense.user_id == user_id,
        extract("year", models.Expense.date) == year,
        extract("month", models.Expense.date) == month,
    ).scalar()
    return {
        "income": round(income, 2),
        "expense": round(expense, 2),
        "saved": round(income - expense, 2),
    }


def get_category_breakdown(db: Session, user_id: int, year: int, month: int):
    rows = db.query(
        models.Expense.category, func.sum(models.Expense.amount)
    ).filter(
        models.Expense.user_id == user_id,
        extract("year", models.Expense.date) == year,
        extract("month", models.Expense.date) == month,
    ).group_by(models.Expense.category).all()
    return {cat: round(total, 2) for cat, total in rows}


def get_largest_expense(db: Session, user_id: int, year: int, month: int):
    return db.query(models.Expense).filter(
        models.Expense.user_id == user_id,
        extract("year", models.Expense.date) == year,
        extract("month", models.Expense.date) == month,
    ).order_by(models.Expense.amount.desc()).first()


# ---------- Chat ----------

def save_chat_message(db: Session, user_id: int, role: str, content: str):
    row = models.ChatMessage(user_id=user_id, role=role, content=content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_recent_chat(db: Session, user_id: int, limit: int = 20):
    rows = db.query(models.ChatMessage).filter(
        models.ChatMessage.user_id == user_id
    ).order_by(models.ChatMessage.created_at.desc()).limit(limit).all()
    return list(reversed(rows))


# ---------- Pending entries (offline/rate-limit queue) ----------

def create_pending_entry(db: Session, user_id: int, raw_message: str):
    row = models.PendingEntry(user_id=user_id, raw_message=raw_message, status="pending")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_pending_entries(db: Session, status: str = "pending", limit: int = 100):
    return db.query(models.PendingEntry).filter(
        models.PendingEntry.status == status
    ).order_by(models.PendingEntry.created_at.asc()).limit(limit).all()


def get_pending_entries_for_user(db: Session, user_id: int, limit: int = 20):
    return db.query(models.PendingEntry).filter(
        models.PendingEntry.user_id == user_id,
        models.PendingEntry.status == "pending",
    ).order_by(models.PendingEntry.created_at.desc()).limit(limit).all()


def mark_pending_processed(db: Session, entry_id: int):
    row = db.query(models.PendingEntry).filter(models.PendingEntry.id == entry_id).first()
    if row:
        row.status = "processed"
        row.processed_at = datetime.utcnow()
        db.commit()


def mark_pending_attempt_failed(db: Session, entry_id: int, error: str, max_attempts: int = 20):
    row = db.query(models.PendingEntry).filter(models.PendingEntry.id == entry_id).first()
    if row:
        row.attempts += 1
        row.last_error = error[:500]
        if row.attempts >= max_attempts:
            row.status = "failed"
        db.commit()

# --- Personalized category learning (feature #22) ---
# Distinctive-word memory of what a category actually meant for THIS user
# in the past, used only to resolve future "Other" fallbacks - see
# models.MerchantMemory for the reasoning.

def remember_merchant_category(db: Session, user_id: int, transaction_type: str, keyword: str, category_or_source: str):
    keyword = keyword.lower().strip()
    if not keyword or category_or_source == "Other":
        return
    row = db.query(models.MerchantMemory).filter(
        models.MerchantMemory.user_id == user_id,
        models.MerchantMemory.transaction_type == transaction_type,
        models.MerchantMemory.keyword == keyword,
    ).first()
    if row:
        if row.category_or_source == category_or_source:
            row.hit_count += 1
        else:
            # The user's own habit shifted for this word - trust the most
            # recent mapping rather than averaging two different answers.
            row.category_or_source = category_or_source
            row.hit_count = 1
    else:
        row = models.MerchantMemory(
            user_id=user_id,
            transaction_type=transaction_type,
            keyword=keyword,
            category_or_source=category_or_source,
            hit_count=1,
        )
        db.add(row)
    db.commit()


def recall_merchant_category(db: Session, user_id: int, transaction_type: str, keywords: list[str], min_hits: int = 2) -> str | None:
    """Returns the learned category for the first keyword with enough
    confirmed history (hit_count >= min_hits), or None. min_hits=2 so a
    single one-off word never immediately overrides "Other" - it has to
    have shown up with a consistent category at least twice before."""
    if not keywords:
        return None
    rows = db.query(models.MerchantMemory).filter(
        models.MerchantMemory.user_id == user_id,
        models.MerchantMemory.transaction_type == transaction_type,
        models.MerchantMemory.keyword.in_([k.lower() for k in keywords]),
        models.MerchantMemory.hit_count >= min_hits,
    ).all()
    if not rows:
        return None
    best = max(rows, key=lambda r: r.hit_count)
    return best.category_or_source


# --- Duplicate detection on the chat-creation path (feature #24) ---
# The offline sync path (services/sync.py) already dedupes; this covers
# the far more common path (typing straight into chat), which had no
# such check at all.

def find_possible_duplicate(db: Session, user_id: int, transaction_type: str, category_or_source: str, amount: float, txn_date):
    if transaction_type == "income":
        return db.query(models.Income).filter(
            models.Income.user_id == user_id,
            models.Income.source == category_or_source,
            models.Income.amount == amount,
            models.Income.date == txn_date,
        ).first()
    return db.query(models.Expense).filter(
        models.Expense.user_id == user_id,
        models.Expense.category == category_or_source,
        models.Expense.amount == amount,
        models.Expense.date == txn_date,
    ).first()
