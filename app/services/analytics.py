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
