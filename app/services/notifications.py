"""
notifications.py
In-app notification helpers (e.g. low-balance alerts surfaced on the
dashboard). Not currently wired into any route (get_smart_suggestion in
analytics.py covers this same signal today) - kept for future use, updated
to the multi-user signature so it doesn't silently break if wired in later.
"""

from sqlalchemy.orm import Session
from app.database import crud
from app.services import currency as currency_service


def check_low_balance_alert(db: Session, user) -> str | None:
    currency = user.currency or "INR"
    threshold = currency_service.convert_amount(user.monthly_alert_amount or 1000.0, "INR", currency)
    balance = currency_service.convert_amount(crud.get_balance(db, user.id), "INR", currency)
    if balance < threshold:
        return f"Balance is below {currency_service.format_amount(user.monthly_alert_amount or 1000.0, currency)} (currently {currency_service.format_amount(crud.get_balance(db, user.id), currency)}). Avoid unnecessary spending."
    return None
