"""
analytics.py
Assembles dashboard data and smart suggestions. Separated from finance.py
since finance.py is transaction read/write and this is read-only aggregation.
"""

from datetime import date
from sqlalchemy.orm import Session

from app.ai import response as ai_response
from app.ai.llm import LLMUnavailableError
from app.database import crud
from app.services import currency as currency_service


def _currency_symbol(code: str | None) -> str:
    mapping = {
        "INR": "Rs.",
        "USD": "$",
        "GBP": "£",
        "JPY": "¥",
        "CNY": "¥",
        "KRW": "₩",
    }
    return mapping.get((code or "INR").upper(), (code or "INR").upper())


def _format_amount(code: str | None, amount: float) -> str:
    symbol = _currency_symbol(code)
    return f"{symbol} {amount:,.2f}"


def get_dashboard_data(db: Session, user) -> dict:
    today = date.today()
    balance = crud.get_balance(db, user.id)
    month_summary = crud.get_month_summary(db, user.id, today.year, today.month)
    timeline = crud.get_timeline(db, user.id, limit=10)
    currency = user.currency or "INR"
    currency_symbol = _currency_symbol(currency)
    return {
        "balance": currency_service.convert_amount(balance, "INR", currency),
        "income": currency_service.convert_amount(month_summary["income"], "INR", currency),
        "expense": currency_service.convert_amount(month_summary["expense"], "INR", currency),
        "saved": currency_service.convert_amount(month_summary["saved"], "INR", currency),
        "currency": currency,
        "currency_symbol": currency_symbol,
        "suggestion": get_smart_suggestion(db, user),
        "recent_timeline": [
            {
                "type": t["type"],
                "amount": currency_service.convert_amount(t["amount"], "INR", currency),
                "label": t["label"],
                "display_label": t.get("display_label") or t["label"],
                "date": str(t["date"]),
            }
            for t in timeline
        ],
    }


def _prev_month(year: int, month: int, back: int) -> tuple[int, int]:
    m = month - back
    y = year
    while m <= 0:
        m += 12
        y -= 1
    return y, m


def _detect_unusual_spending(db: Session, user, this_month_breakdown: dict, currency: str) -> str:
    """Combines Spending Pattern Detection and Smart Saving Suggestions -
    spotting a category that's unusually elevated vs. the user's own
    recent average IS the actionable saving opportunity, so one rule
    covers both rather than two separate heuristics saying the same thing
    two different ways.

    Requires a meaningful baseline (>=200 in base currency across the last
    2 months) before calling anything "unusual" - a category that simply
    didn't exist before isn't a pattern, it's a new expense, and flagging
    every first-time category would just be noise."""
    today = date.today()
    y1, m1 = _prev_month(today.year, today.month, 1)
    y2, m2 = _prev_month(today.year, today.month, 2)
    prev1 = crud.get_category_breakdown(db, user.id, y1, m1)
    prev2 = crud.get_category_breakdown(db, user.id, y2, m2)
    if not prev1 and not prev2:
        return ""

    best = None
    for cat, amount in this_month_breakdown.items():
        avg = (prev1.get(cat, 0.0) + prev2.get(cat, 0.0)) / 2
        if avg < 200.0:
            continue
        if amount >= avg * 1.5 and (amount - avg) >= 300.0:
            ratio = amount / avg
            if not best or ratio > best[2]:
                best = (cat, amount, ratio, avg)
    if not best:
        return ""

    cat, amount, ratio, avg = best
    pct = round((ratio - 1) * 100)
    amount_c = currency_service.convert_amount(amount, "INR", currency)
    avg_c = currency_service.convert_amount(avg, "INR", currency)
    return (
        f"{cat} spending is up {pct}% this month ({_format_amount(currency, amount_c)} vs your recent average of "
        f"{_format_amount(currency, avg_c)}) - worth a look if it wasn't planned, and an easy place to cut back if you need to save more."
    )


def get_smart_suggestion(db: Session, user) -> str:
    """Generates one short insight. Cheap heuristics first; falls back to the
    LLM only if nothing rule-based stands out, to avoid a cloud API call on
    every single dashboard load (also helps stay well under the free-tier
    daily request caps)."""
    today = date.today()
    summary = crud.get_month_summary(db, user.id, today.year, today.month)
    breakdown = crud.get_category_breakdown(db, user.id, today.year, today.month)
    balance = crud.get_balance(db, user.id)
    currency = user.currency or "INR"

    alert_amount = currency_service.convert_amount(user.monthly_alert_amount or 1000.0, "INR", currency)
    converted_balance = currency_service.convert_amount(balance, "INR", currency)
    if converted_balance < alert_amount:
        return (
            f"Your balance is {_format_amount(currency, converted_balance)} - below your "
            f"{_format_amount(currency, alert_amount)} alert threshold. Might be worth holding off on non-essentials."
        )

    if breakdown:
        top_cat = max(breakdown, key=breakdown.get)
        top_amount = breakdown[top_cat]
        if summary["income"] > 0 and top_amount > 0.3 * summary["income"]:
            pct = round((top_amount / summary["income"]) * 100)
            return f"{top_cat} spending is {_format_amount(currency, currency_service.convert_amount(top_amount, 'INR', currency))} this month - {pct}% of your income so far."

    unusual = _detect_unusual_spending(db, user, breakdown, currency)
    if unusual:
        return unusual

    context = {
        "balance": currency_service.convert_amount(balance, "INR", currency),
        "this_month": {
            "income": currency_service.convert_amount(summary["income"], "INR", currency),
            "expense": currency_service.convert_amount(summary["expense"], "INR", currency),
            "saved": currency_service.convert_amount(summary["saved"], "INR", currency),
        },
        "category_breakdown": {
            key: currency_service.convert_amount(value, "INR", currency) for key, value in breakdown.items()
        },
        "currency": currency,
        "currency_symbol": _currency_symbol(currency),
    }
    try:
        return ai_response.generate_suggestion(context)
    except LLMUnavailableError:
        return ""
    except Exception:
        return ""
