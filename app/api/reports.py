"""
api/reports.py
Report data + export endpoints, scoped per user.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import date

from app.database.database import get_db
from app.database import models
from app.auth.auth import get_current_user
from app.services import reports as reports_service
from app.services import export as export_service

router = APIRouter()


@router.get("/reports")
def get_report(
    request: Request,
    year: int = Query(default=None),
    month: int = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    today = date.today()
    y = year or today.year
    m = month or today.month
    return reports_service.get_full_report(db, user, y, m)


@router.get("/reports/months")
def available_months(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return reports_service.list_available_months(db, user.id)


@router.get("/export/csv")
def export_csv(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    path = export_service.export_csv(db, user.id)
    return FileResponse(path, filename="stash_export.csv", media_type="text/csv")


@router.get("/export/excel")
def export_excel(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    path = export_service.export_excel(db, user.id)
    return FileResponse(
        path, filename="stash_export.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/export/pdf")
def export_pdf(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    path = export_service.export_pdf(db, user.id)
    return FileResponse(path, filename="stash_export.pdf", media_type="application/pdf")
