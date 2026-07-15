"""helpers.py - small shared utilities"""

from datetime import date


def format_currency(amount: float, symbol: str = "Rs.") -> str:
    return f"{symbol}{amount:,.2f}"


def today_iso() -> str:
    return date.today().isoformat()
