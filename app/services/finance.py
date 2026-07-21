"""
finance.py
Core business logic for transactions. This is where the correction
disambiguation safeguard lives: if a correction message could match more
than one transaction, we do NOT silently guess. We return candidates and
ask the user to confirm.

Multi-user note: every function here takes user_id and threads it into
every crud.* call, so one family member's "petrol was actually 600"
correction can only ever match THEIR petrol transactions.
"""

from datetime import date
from sqlalchemy.orm import Session

from app.database import crud
from app.services import currency as currency_service
from app.services import recurring as recurring_service


def _fmt_amount(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_money(code: str | None, value: float) -> str:
    return currency_service.format_amount(value, code)


def _to_base(amount: float, currency: str | None) -> float:
    return currency_service.convert_amount(amount, currency, currency_service.BASE_CURRENCY)


def _from_base(amount: float, currency: str | None) -> float:
    return currency_service.convert_amount(amount, currency_service.BASE_CURRENCY, currency)


def _display_label(txn_type: str, label: str, description: str | None) -> str:
    return crud.resolve_display_label(txn_type, label, description)


def _candidate_rows(
    db: Session,
    user_id: int,
    txn_type: str,
    category_or_source: str | None,
    search_terms: str,
    target_date: date | None,
    days: int = 14,
    limit: int = 10,
):
    if txn_type == "income":
        candidates = crud.find_recent_income_by_source(db, user_id, category_or_source, days=days, limit=limit)
    else:
        candidates = crud.find_recent_expenses_by_category(db, user_id, category_or_source, days=days, limit=limit)

    if target_date:
        dated = [row for row in candidates if row.date == target_date]
        if dated:
            candidates = dated

    if candidates or not search_terms:
        return candidates

    if txn_type == "income":
        recent = crud.find_recent_income_by_source(db, user_id, None, days=days, limit=20)
        return [
            row for row in recent
            if search_terms in (row.description or "").lower() or search_terms in row.source.lower()
        ]

    recent = crud.find_recent_expenses_by_category(db, user_id, None, days=days, limit=20)
    return [
        row for row in recent
        if search_terms in (row.description or "").lower() or search_terms in row.category.lower()
    ]


def create_transactions(db: Session, user_id: int, transactions: list[dict], currency: str | None = None) -> list[dict]:
    created = []
    for t in transactions:
        base_amount = _to_base(t["amount"], currency)
        payment_method = t.get("payment_method")
        if t["type"] == "income":
            row = crud.create_income(
                db,
                user_id,
                amount=base_amount,
                source=t["category_or_source"],
                description=t["description"],
                txn_date=t["date"],
                payment_method=payment_method,
            )
            created.append(
                {
                    "type": "income",
                    "id": row.id,
                    "amount": row.amount,
                    "label": row.source,
                    "display_label": _display_label("income", row.source, row.description),
                    "date": str(row.date),
                    "payment_method": row.payment_method,
                }
            )
        else:
            row = crud.create_expense(
                db,
                user_id,
                amount=base_amount,
                category=t["category_or_source"],
                description=t["description"],
                txn_date=t["date"],
                payment_method=payment_method,
            )
            created.append(
                {
                    "type": "expense",
                    "id": row.id,
                    "amount": row.amount,
                    "label": row.category,
                    "display_label": _display_label("expense", row.category, row.description),
                    "date": str(row.date),
                    "payment_method": row.payment_method,
                }
            )
    return created


def format_transaction_reply(created: list[dict], balance: float | None = None, currency: str | None = None) -> str:
    if len(created) == 1:
        t = created[0]
        verb = "Added income" if t["type"] == "income" else "Expense added"
        reply = f"{verb}: {_fmt_money(currency, t['amount'])} ({t.get('display_label') or t['label']})"
        if balance is not None:
            reply += f"\nUpdated balance: {_fmt_money(currency, balance)}"
            if balance <= 0:
                reply += f"\nYour balance hit {_fmt_money(currency, 0)}."
        return reply

    lines = ["Got it, logged these:"]
    for t in created:
        sign = "+" if t["type"] == "income" else "-"
        lines.append(f"- {sign} {_fmt_money(currency, t['amount'])} ({t.get('display_label') or t['label']}) on {t['date']}")
    if balance is not None:
        lines.append(f"Updated balance: {_fmt_money(currency, balance)}")
        if balance <= 0:
            lines.append(f"Your balance hit {_fmt_money(currency, 0)}.")
    return "\n".join(lines)


def apply_correction(db: Session, user_id: int, correction: dict, currency: str | None = None) -> dict:
    """
    Finds candidate transactions matching the correction's type/category/date
    window. If exactly one match, apply directly. If multiple, return
    candidates for user confirmation. If none, say so plainly.
    """
    txn_type = correction["type"]
    cat = correction["category_or_source"]
    search_terms = (correction.get("search_terms") or "").lower()
    target_date = correction.get("date")

    candidates = _candidate_rows(db, user_id, txn_type, cat, search_terms, target_date)

    if not candidates:
        return {
            "intent": "correction",
            "reply": "I couldn't find a matching transaction to correct in the last 14 days. Could you give a bit more detail?",
            "data": None,
            "needs_confirmation": False,
            "candidates": None,
        }

    if len(candidates) == 1:
        row = candidates[0]
        old_amount = row.amount
        new_amount_base = _to_base(correction["new_amount"], currency)
        if txn_type == "income":
            crud.update_income(db, user_id, row.id, amount=new_amount_base)
        else:
            crud.update_expense(db, user_id, row.id, amount=new_amount_base)
        label = _display_label(txn_type, row.source if txn_type == "income" else row.category, row.description)
        balance = crud.get_balance(db, user_id)
        return {
            "intent": "correction",
            "reply": (
                f"Updated {label}: {_fmt_money(currency, old_amount)} -> {_fmt_money(currency, new_amount_base)}\n"
                f"Updated balance: {_fmt_money(currency, balance)}"
            )
            + (f"\nYour balance hit {_fmt_money(currency, 0)}." if balance <= 0 else ""),
            "data": {
                "id": row.id,
                "type": txn_type,
                "old_amount": old_amount,
                "new_amount": correction["new_amount"],
            },
            "needs_confirmation": False,
            "candidates": None,
        }

    options = []
    for row in candidates:
        label = _display_label(txn_type, row.source if txn_type == "income" else row.category, row.description)
        options.append(
            {
                "id": row.id,
                "type": txn_type,
                "amount": row.amount,
                "label": label,
                "date": str(row.date),
                "description": row.description,
            }
        )
    return {
        "intent": "correction",
        "reply": f"I found {len(options)} matching transactions - which one did you mean?",
        "data": {"pending_new_amount": correction["new_amount"]},
        "needs_confirmation": True,
        "candidates": options,
    }


def apply_delete(db: Session, user_id: int, delete_request: dict, currency: str | None = None) -> dict:
    txn_type = delete_request["type"]
    cat = delete_request["category_or_source"]
    search_terms = (delete_request.get("search_terms") or "").lower()
    target_date = delete_request.get("date")

    candidates = _candidate_rows(db, user_id, txn_type, cat, search_terms, target_date)

    if not candidates:
        return {
            "intent": "delete",
            "reply": "I couldn't find a matching transaction to delete in the last 14 days. Could you give a bit more detail?",
            "data": None,
            "needs_confirmation": False,
            "candidates": None,
        }

    if len(candidates) == 1:
        row = candidates[0]
        label = _display_label(txn_type, row.source if txn_type == "income" else row.category, row.description)
        if txn_type == "income":
            crud.delete_income(db, user_id, row.id)
        else:
            crud.delete_expense(db, user_id, row.id)
        balance = crud.get_balance(db, user_id)
        reply = f"Deleted {label} ({row.date})."
        reply += f"\nUpdated balance: {_fmt_money(currency, balance)}"
        if balance <= 0:
            reply += f"\nYour balance hit {_fmt_money(currency, 0)}."
        return {
            "intent": "delete",
            "reply": reply,
            "data": {"id": row.id, "type": txn_type},
            "needs_confirmation": False,
            "candidates": None,
        }

    options = []
    for row in candidates:
        label = _display_label(txn_type, row.source if txn_type == "income" else row.category, row.description)
        options.append(
            {
                "id": row.id,
                "type": txn_type,
                "amount": row.amount,
                "label": label,
                "date": str(row.date),
                "description": row.description,
            }
        )
    return {
        "intent": "delete",
        "reply": f"I found {len(options)} matching transactions - which one should I delete?",
        "data": {"pending_action": "delete"},
        "needs_confirmation": True,
        "candidates": options,
    }


def confirm_correction(db: Session, user_id: int, txn_id: int, txn_type: str, new_amount: float, currency: str | None = None) -> dict:
    new_amount_base = _to_base(new_amount, currency)
    if txn_type == "income":
        row = crud.update_income(db, user_id, txn_id, amount=new_amount_base)
        label = _display_label("income", row.source, row.description) if row else "transaction"
    else:
        row = crud.update_expense(db, user_id, txn_id, amount=new_amount_base)
        label = _display_label("expense", row.category, row.description) if row else "transaction"
    if not row:
        return {"reply": "Couldn't find that transaction anymore - it may have been removed."}
    reply = f"Updated {label} to {_fmt_money(currency, new_amount_base)}."
    balance = crud.get_balance(db, user_id)
    reply += f"\nUpdated balance: {_fmt_money(currency, balance)}"
    if balance <= 0:
        reply += f"\nYour balance hit {_fmt_money(currency, 0)}."
    return {"reply": reply}


def build_qa_context(db: Session, user_id: int, question: str, currency: str | None = None) -> dict:
    recurring_service.sync_due_recurring(db, user_id)
    today = date.today()
    balance = crud.get_balance(db, user_id)
    this_month = crud.get_month_summary(db, user_id, today.year, today.month)
    last_month_date = (today.replace(day=1) - __import__("datetime").timedelta(days=1))
    last_month = crud.get_month_summary(db, user_id, last_month_date.year, last_month_date.month)
    category_breakdown = crud.get_category_breakdown(db, user_id, today.year, today.month)
    largest = crud.get_largest_expense(db, user_id, today.year, today.month)
    timeline = crud.get_timeline(db, user_id, limit=30)
    recent_chat = crud.get_recent_chat(db, user_id, limit=11)
    if recent_chat and recent_chat[-1].role == "user" and recent_chat[-1].content == question:
        recent_chat = recent_chat[:-1]
    recent_chat = recent_chat[-10:]

    active_currency = currency or "INR"
    converted_breakdown = {
        key: _from_base(value, active_currency) for key, value in category_breakdown.items()
    }

    return {
        "currency": active_currency,
        "currency_symbol": currency_service.currency_symbol(active_currency),
        "current_balance": _from_base(balance, active_currency),
        "this_month": {
            "income": _from_base(this_month["income"], active_currency),
            "expense": _from_base(this_month["expense"], active_currency),
            "saved": _from_base(this_month["saved"], active_currency),
        },
        "last_month": {
            "income": _from_base(last_month["income"], active_currency),
            "expense": _from_base(last_month["expense"], active_currency),
            "saved": _from_base(last_month["saved"], active_currency),
        },
        "this_month_category_breakdown": converted_breakdown,
        "largest_expense_this_month": (
            {"category": largest.category, "amount": _from_base(largest.amount, active_currency), "date": str(largest.date)}
            if largest
            else None
        ),
        "recent_transactions": [
            {
                "type": t["type"],
                "amount": _from_base(t["amount"], active_currency),
                "label": t.get("display_label") or t["label"],
                "date": str(t["date"]),
            }
            for t in timeline
        ],
        "recent_chat_memory": [
            {"role": row.role, "content": row.content, "created_at": str(row.created_at)}
            for row in recent_chat
        ],
    }


def build_report(db: Session, user_id: int, message: str, currency: str | None = None) -> dict:
    import calendar

    recurring_service.sync_due_recurring(db, user_id)
    today = date.today()
    year, month = today.year, today.month
    lowered = message.lower()
    for m_idx in range(1, 13):
        m_name = calendar.month_name[m_idx].lower()
        if m_name in lowered:
            month = m_idx
            year = today.year if month <= today.month else today.year - 1
            break

    summary = crud.get_month_summary(db, user_id, year, month)
    breakdown = crud.get_category_breakdown(db, user_id, year, month)
    largest = crud.get_largest_expense(db, user_id, year, month)
    most_used_category = max(breakdown, key=breakdown.get) if breakdown else None
    active_currency = currency or "INR"
    converted_summary = {
        "income": _from_base(summary["income"], active_currency),
        "expense": _from_base(summary["expense"], active_currency),
        "saved": _from_base(summary["saved"], active_currency),
    }
    converted_breakdown = {key: _from_base(value, active_currency) for key, value in breakdown.items()}

    summary_text = (
        f"{calendar.month_name[month]} {year}: Income {_fmt_money(active_currency, summary['income'])}, "
        f"Expense {_fmt_money(active_currency, summary['expense'])}, Saved {_fmt_money(active_currency, summary['saved'])}."
    )
    if largest:
        summary_text += f" Largest expense: {largest.category} {_fmt_money(active_currency, largest.amount)}."

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "income": converted_summary["income"],
        "expense": converted_summary["expense"],
        "saved": converted_summary["saved"],
        "category_breakdown": converted_breakdown,
        "largest_expense": (
            {"category": largest.category, "amount": _from_base(largest.amount, active_currency)} if largest else None
        ),
        "most_used_category": most_used_category,
        "summary_text": summary_text,
    }
