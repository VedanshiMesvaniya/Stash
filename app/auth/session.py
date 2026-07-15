"""
session.py
Thin helpers around Starlette's signed-cookie session (added via
SessionMiddleware in main.py). Multi-user note: the session now stores
user_id, not just a boolean - that's what makes every downstream query
scoped to "this specific family member's data" instead of one shared pot.
"""

from starlette.requests import Request


def login_session(request: Request, user_id: int, username: str):
    request.session["user_id"] = user_id
    request.session["username"] = username


def logout_session(request: Request):
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    return request.session.get("user_id") is not None


def current_user_id(request: Request) -> int | None:
    return request.session.get("user_id")
