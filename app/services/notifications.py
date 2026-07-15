"""
notifications.py
In-app notification helpers (e.g. low-balance alerts surfaced on the
dashboard). Not currently wired into any route (get_smart_suggestion in
analytics.py covers this same signal today) - kept for future use, updated
to the multi-user signature so it doesn't silently break if wired in later.
"""

from sqlalchemy.orm import Session
from app.database import crud


def check_low_balance_alert(db: Session, user) -> str | None:
    threshold = user.monthly_alert_amount or 1000.0
    balance = crud.get_balance(db, user.id)
    if balance < threshold:
        return f"Balance is below Rs. {threshold:,.2f} (currently Rs. {balance:,.2f}). Avoid unnecessary spending."
    return None
