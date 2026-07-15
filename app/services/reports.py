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


def get_full_report(db: Session, user, year: int, month: int) -> dict:
    summary = crud.get_month_summary(db, user.id, year, month)
    breakdown = crud.get_category_breakdown(db, user.id, year, month)
    largest = crud.get_largest_expense(db, user.id, year, month)

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
        "income": summary["income"], "expense": summary["expense"], "saved": summary["saved"],
        "currency": user.currency or "INR",
        "category_breakdown": breakdown,  # for pie + bar chart
        "daily_trend": daily,  # for line chart
        "largest_expense": (
            {"category": largest.category, "amount": largest.amount, "date": str(largest.date)}
            if largest else None
        ),
        "most_used_category": max(breakdown, key=breakdown.get) if breakdown else None,
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
