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


def get_category_trend_history(db: Session, user_id: int, currency: str, months: int = 4) -> dict[str, list[float]]:
    """category -> list of that category's spend for each of the last
    `months` months (oldest first, current month last), converted to the
    display currency. Shared building block for detect_spending_trends."""
    today = date.today()
    month_points = []
    for back in range(months - 1, -1, -1):
        y, m = _prev_month(today.year, today.month, back)
        month_points.append(crud.get_category_breakdown(db, user_id, y, m))

    categories = set()
    for breakdown in month_points:
        categories.update(breakdown.keys())

    return {
        cat: [currency_service.convert_amount(breakdown.get(cat, 0.0), "INR", currency) for breakdown in month_points]
        for cat in categories
    }


def detect_spending_trends(db: Session, user_id: int, currency: str = "INR", months: int = 4, min_avg: float = 200.0) -> list[dict]:
    """Feature AI-33: Spending Pattern Detection. A dedicated MULTI-month
    trend detector - genuinely different from _detect_unusual_spending,
    which only ever compares the current month against a 2-month average
    to catch a single spike. A category can be "unusual this month"
    without trending at all (one-off spike then back to normal), and can
    be steadily trending up for months without any single month looking
    unusual enough to trip that check. This looks at the whole window and
    only flags a category whose spend moved in the SAME direction every
    consecutive month - a zigzag isn't a pattern, even if the net change
    over the window is large.

    Returns a list of {"category", "direction", "monthly_amounts",
    "change_pct"} dicts, sorted by the strength of the change."""
    history = get_category_trend_history(db, user_id, currency, months=months)
    min_avg_c = currency_service.convert_amount(min_avg, "INR", currency)

    trends = []
    for cat, amounts in history.items():
        if len(amounts) < 3:
            continue
        avg = sum(amounts) / len(amounts)
        if avg < min_avg_c:
            continue  # too small a category to call a "pattern" - just noise

        diffs = [amounts[i + 1] - amounts[i] for i in range(len(amounts) - 1)]
        if all(d > 0 for d in diffs):
            direction = "increasing"
        elif all(d < 0 for d in diffs):
            direction = "decreasing"
        else:
            continue  # not consistently one direction every month - skip

        change_pct = round(((amounts[-1] - amounts[0]) / amounts[0]) * 100) if amounts[0] else None
        trends.append({
            "category": cat,
            "direction": direction,
            "monthly_amounts": [round(a, 2) for a in amounts],
            "change_pct": change_pct,
        })

    trends.sort(key=lambda t: abs(t["change_pct"] or 0), reverse=True)
    return trends


_DISCRETIONARY_CATEGORIES = ("Entertainment", "Shopping", "Snacks", "Tea")


def get_savings_suggestions(db: Session, user_id: int, currency: str = "INR", cut_pct: int = 20) -> list[str]:
    """Feature AI-34: Smart Saving Suggestions. A dedicated savings-
    opportunity recommender - distinct from _detect_unusual_spending's
    "this looks elevated" nudge, which fires on ANY category (including
    ones you can't really cut, like Medical or Bills) and only when it's
    abnormal versus your own recent average. This instead always looks at
    DISCRETIONARY categories specifically (the ones a person can actually
    choose to spend less on) and, when there's an active savings goal,
    ties the suggestion to a concrete number against that goal rather
    than a generic "spend less" nudge."""
    currency = currency or "INR"
    today = date.today()
    breakdown = crud.get_category_breakdown(db, user_id, today.year, today.month)
    discretionary = {cat: amt for cat, amt in breakdown.items() if cat in _DISCRETIONARY_CATEGORIES and amt > 0}
    if not discretionary:
        return []

    top_cat = max(discretionary, key=discretionary.get)
    top_amount_c = currency_service.convert_amount(discretionary[top_cat], "INR", currency)
    min_meaningful_c = currency_service.convert_amount(300.0, "INR", currency)
    if top_amount_c < min_meaningful_c:
        return []  # too small an amount for a cut to be worth suggesting

    cut_amount_c = round(top_amount_c * cut_pct / 100, 2)
    cut_str = _format_amount(currency, cut_amount_c)

    goal = crud.get_savings_goal(db, user_id)
    if goal and goal.target_amount:
        progress = crud.get_savings_progress_since(db, user_id, goal.created_at)
        remaining = goal.target_amount - progress
        if remaining > 0:
            remaining_c = currency_service.convert_amount(remaining, "INR", currency)
            goal_str = _format_amount(currency, currency_service.convert_amount(goal.target_amount, "INR", currency))
            pct_of_remaining = round((cut_amount_c / remaining_c) * 100) if remaining_c else None
            if pct_of_remaining:
                return [
                    f"Cutting {top_cat} spending by {cut_pct}% (~{cut_str}/month) would put you about "
                    f"{pct_of_remaining}% closer to your {goal_str} savings goal each month you keep it up."
                ]

    return [
        f"{top_cat} is your top discretionary spend this month at {_format_amount(currency, top_amount_c)} - "
        f"trimming it by {cut_pct}% would free up roughly {cut_str}."
    ]


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
