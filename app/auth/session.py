"""
session.py
Thin helpers around Starlette's signed-cookie session (added via
SessionMiddleware in main.py). Multi-user note: the session now stores
user_id, not just a boolean - that's what makes every downstream query
scoped to "this specific family member's data" instead of one shared pot.
"""

import time

from starlette.requests import Request

SESSION_MAX_AGE_SECONDS = 72 * 60 * 60


def _session_expired(request: Request) -> bool:
    login_at = request.session.get("login_at")
    if not login_at:
        return True
    try:
        return (time.time() - float(login_at)) >= SESSION_MAX_AGE_SECONDS
    except (TypeError, ValueError):
        return True


def login_session(request: Request, user_id: int, username: str):
    request.session["user_id"] = user_id
    request.session["username"] = username
    request.session["login_at"] = time.time()


def logout_session(request: Request):
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    if request.session.get("user_id") is None:
        return False
    if _session_expired(request):
        request.session.clear()
        return False
    return True


def current_user_id(request: Request) -> int | None:
    if not is_authenticated(request):
        return None
    return request.session.get("user_id")
