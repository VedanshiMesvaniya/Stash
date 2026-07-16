"""
main.py
Stash application entry point. Run with: uvicorn app.main:app --reload
(local) or via the Render start command in production.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.database.database import init_db, get_db, SessionLocal
from app.database import seed, crud
from app.auth.session import is_authenticated, SESSION_MAX_AGE_SECONDS
from app.ai import extractor
from app.ai.llm import LLMUnavailableError
from app.services import finance as finance_service
from app.api.routes import api_router
from app.api import auth as auth_routes

logger = logging.getLogger("stash")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# No fallback on purpose: a finance app with a guessable/default signing key
# is a real vulnerability, so fail loudly at startup instead of silently
# running with a public secret.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. Generate one with "
        "`python -c \"import secrets; print(secrets.token_hex(32))\"` and set it "
        "as an env var before starting the app - this is not optional for a "
        "deployed finance app."
    )

IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"
PENDING_RETRY_INTERVAL_SECONDS = int(os.getenv("PENDING_RETRY_INTERVAL_SECONDS", "300"))

app = FastAPI(title="Stash - AI Personal Wallet")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=SESSION_MAX_AGE_SECONDS,
    session_cookie="stash_session",
    same_site="lax",
    https_only=IS_PRODUCTION,
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.include_router(api_router)
app.include_router(auth_routes.router)

REACT_INDEX = os.path.join(BASE_DIR, "static", "react", "index.html")

_pending_retry_task = None


async def _retry_pending_entries_loop():
    """Background job: every PENDING_RETRY_INTERVAL_SECONDS, retries any
    chat messages that got queued into pending_entries because both Groq
    and OpenRouter were down/rate-limited when they were first sent. Runs
    forever as an asyncio task started on app startup; survives fine across
    normal request traffic since it's just a loop, not tied to any request.
    """
    while True:
        await asyncio.sleep(PENDING_RETRY_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            entries = crud.get_pending_entries(db, status="pending", limit=50)
            for entry in entries:
                try:
                    transactions = extractor.extract_transactions(entry.raw_message)
                    if transactions:
                        finance_service.create_transactions(db, entry.user_id, transactions)
                    crud.mark_pending_processed(db, entry.id)
                except LLMUnavailableError as e:
                    crud.mark_pending_attempt_failed(db, entry.id, str(e))
                except Exception as e:  # noqa: BLE001 - log and move to next entry, don't crash the loop
                    logger.exception("Error retrying pending entry %s", entry.id)
                    crud.mark_pending_attempt_failed(db, entry.id, str(e))
        finally:
            db.close()


@app.on_event("startup")
async def on_startup():
    global _pending_retry_task
    init_db()
    db = SessionLocal()
    try:
        seed.seed_categories(db)
        seed.seed_users(db)
    finally:
        db.close()
    _pending_retry_task = asyncio.create_task(_retry_pending_entries_loop())


@app.on_event("shutdown")
async def on_shutdown():
    if _pending_retry_task:
        _pending_retry_task.cancel()


def _guard(request: Request):
    """Returns a RedirectResponse if the request isn't logged in, else None.
    No first-run/setup redirect anymore - accounts are pre-seeded."""
    if not is_authenticated(request) and request.url.path != "/login":
        return RedirectResponse(url="/login")
    return None


def _frontend_response(request: Request, template_name: str, context: dict):
    if os.path.exists(REACT_INDEX):
        return FileResponse(REACT_INDEX)
    return templates.TemplateResponse(template_name, context)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    error = request.query_params.get("error")
    return _frontend_response(request, "login.html", {"request": request, "mode": "login", "error": error})


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return _frontend_response(request, "dashboard.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return _frontend_response(request, "chat.html", {"request": request})


@app.get("/timeline", response_class=HTMLResponse)
def timeline_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return _frontend_response(request, "timeline.html", {"request": request})


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return _frontend_response(request, "reports.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return _frontend_response(request, "settings.html", {"request": request})
