"""
api/routes.py
Aggregates all API sub-routers under a single /api prefix (auth routes are
mounted separately at root since they handle redirects for HTML forms).
"""

from fastapi import APIRouter
from . import finance, reports, settings, recurring

api_router = APIRouter(prefix="/api")
api_router.include_router(finance.router, tags=["finance"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(recurring.router, tags=["recurring"])
