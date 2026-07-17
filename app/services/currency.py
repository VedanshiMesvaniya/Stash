"""
currency.py
Shared currency helpers for live conversion and display formatting.

The database keeps a single base currency (INR). When the user switches the
active display currency, we convert amounts at read/write boundaries using a
live exchange-rate lookup with a small in-memory cache.
"""

from __future__ import annotations

from time import monotonic

import httpx

BASE_CURRENCY = "INR"
RATE_TTL_SECONDS = 60 * 60

_RATE_CACHE: dict[tuple[str, str], tuple[float, float]] = {}

_CURRENCY_SYMBOLS = {
    "INR": "Rs.",
    "USD": "$",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "KRW": "₩",
    "EUR": "€",
}


def normalize_currency(code: str | None) -> str:
    if not code:
        return BASE_CURRENCY
    value = code.strip().upper()
    aliases = {
        "UK": "GBP",
        "JAPAN": "JPY",
        "CHINA": "CNY",
        "KOREA": "KRW",
    }
    return aliases.get(value, value)


def currency_symbol(code: str | None) -> str:
    return _CURRENCY_SYMBOLS.get(normalize_currency(code), normalize_currency(code))


def _get_cached_rate(from_currency: str, to_currency: str) -> float | None:
    cached = _RATE_CACHE.get((from_currency, to_currency))
    if not cached:
        return None
    cached_at, rate = cached
    if monotonic() - cached_at > RATE_TTL_SECONDS:
        return None
    return rate


def _store_rate(from_currency: str, to_currency: str, rate: float) -> None:
    _RATE_CACHE[(from_currency, to_currency)] = (monotonic(), rate)


def get_rate(from_currency: str | None, to_currency: str | None) -> float:
    source = normalize_currency(from_currency)
    target = normalize_currency(to_currency)
    if source == target:
        return 1.0

    cached = _get_cached_rate(source, target)
    if cached is not None:
        return cached

    url = "https://api.frankfurter.dev/v1/latest"
    try:
        response = httpx.get(url, params={"base": source, "symbols": target}, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
        rate = float(payload["rates"][target])
    except Exception:
        rate = 1.0

    _store_rate(source, target, rate)
    return rate


def convert_amount(amount: float, from_currency: str | None, to_currency: str | None) -> float:
    return float(amount) * get_rate(from_currency, to_currency)


def format_amount(amount: float, to_currency: str | None, from_currency: str | None = BASE_CURRENCY) -> str:
    converted = convert_amount(amount, from_currency, to_currency)
    return f"{currency_symbol(to_currency)} {converted:,.2f}"
