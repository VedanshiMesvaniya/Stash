"""
reports.py
Builds report payloads for the Reports page, including chart-ready series
for Chart.js (pie, bar, daily trend). Scoped per user.
"""

from sqlalchemy.orm import Session
from sqlalchemy import extract
from datetime import date
import calendar
from app.database import crud, models
from app.services import currency as currency_service


def get_full_report(db: Session, user, year: int, month: int) -> dict:
    summary = crud.get_month_summary(db, user.id, year, month)
    breakdown = crud.get_category_breakdown(db, user.id, year, month)
    largest = crud.get_largest_expense(db, user.id, year, month)
    currency = user.currency or "INR"

    # Daily trend: sum of expenses per day of month
    days_in_month = calendar.monthrange(year, month)[1]
    daily = {d: 0.0 for d in range(1, days_in_month + 1)}
    rows = db.query(models.Expense).filter(
        models.Expense.user_id == user.id,
        extract("year", models.Expense.date) == year,
        extract("month", models.Expense.date) == month,
    ).all()
    for r in rows:
        daily[r.date.day] = daily.get(r.date.day, 0.0) + r.amount

    return {
        "year": year, "month": month, "month_name": calendar.month_name[month],
        "income": currency_service.convert_amount(summary["income"], "INR", currency),
        "expense": currency_service.convert_amount(summary["expense"], "INR", currency),
        "saved": currency_service.convert_amount(summary["saved"], "INR", currency),
        "currency": currency,
        "category_breakdown": {k: currency_service.convert_amount(v, "INR", currency) for k, v in breakdown.items()},
        "daily_trend": {k: currency_service.convert_amount(v, "INR", currency) for k, v in daily.items()},
        "largest_expense": (
            {"category": largest.category, "amount": currency_service.convert_amount(largest.amount, "INR", currency), "date": str(largest.date)}
            if largest else None
        ),
        "most_used_category": max(breakdown, key=breakdown.get) if breakdown else None,
    }


def get_trend(db: Session, user, year: int, month: int, period: str = "monthly") -> dict:
    """Trend series for the dashboard/reports bar chart. `period` controls
    the bucketing:
      - "monthly" (default): one bucket per day of the selected month
      - "weekly": the selected month's days grouped into 7-day buckets
      - "yearly": one bucket per month of the selected year
    Always returns expense totals (matches what the old Daily Trend line
    chart showed) in the user's display currency.
    """
    currency = user.currency or "INR"
    period = period if period in ("monthly", "weekly", "yearly") else "monthly"

    if period == "yearly":
        totals = {m: 0.0 for m in range(1, 13)}
        rows = db.query(models.Expense).filter(
            models.Expense.user_id == user.id,
            extract("year", models.Expense.date) == year,
        ).all()
        for r in rows:
            totals[r.date.month] = totals.get(r.date.month, 0.0) + r.amount
        entries = [
            [calendar.month_abbr[m], currency_service.convert_amount(v, "INR", currency)]
            for m, v in sorted(totals.items())
        ]
    else:
        days_in_month = calendar.monthrange(year, month)[1]
        daily = {d: 0.0 for d in range(1, days_in_month + 1)}
        rows = db.query(models.Expense).filter(
            models.Expense.user_id == user.id,
            extract("year", models.Expense.date) == year,
            extract("month", models.Expense.date) == month,
        ).all()
        for r in rows:
            daily[r.date.day] = daily.get(r.date.day, 0.0) + r.amount

        if period == "weekly":
            weekly = {}
            for day, value in sorted(daily.items()):
                bucket = f"Week {((day - 1) // 7) + 1}"
                weekly[bucket] = weekly.get(bucket, 0.0) + value
            entries = [[label, currency_service.convert_amount(v, "INR", currency)] for label, v in weekly.items()]
        else:
            entries = [[str(day), currency_service.convert_amount(v, "INR", currency)] for day, v in sorted(daily.items())]

    return {
        "period": period,
        "year": year,
        "month": month,
        "currency": currency,
        "entries": entries,
    }


def list_available_months(db: Session, user_id: int) -> list[dict]:
    """Returns distinct year/month combos that have any transactions, for the
    report page's month picker."""
    income_months = db.query(models.Income.year, models.Income.month).filter(
        models.Income.user_id == user_id
    ).distinct().all()
    expense_months = db.query(models.Expense.year, models.Expense.month).filter(
        models.Expense.user_id == user_id
    ).distinct().all()
    combos = sorted(set(income_months) | set(expense_months), reverse=True)
    return [{"year": y, "month": m, "label": f"{calendar.month_name[m]} {y}"} for y, m in combos]
