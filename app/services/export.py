"""
export.py
CSV / Excel / PDF export of the transaction timeline, scoped per user so
one family member can never export another's data.
"""

import os
import csv
from datetime import datetime
from sqlalchemy.orm import Session
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.database import crud

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")


def _rows(db: Session, user_id: int):
    timeline = crud.get_timeline(db, user_id, limit=10000)
    return [
        {"Date": str(t["date"]), "Type": t["type"], "Category/Source": t.get("display_label") or t["label"],
         "Amount": t["amount"], "Description": t["description"] or ""}
        for t in timeline
    ]


def export_csv(db: Session, user_id: int) -> str:
    rows = _rows(db, user_id)
    path = os.path.join(EXPORT_DIR, "csv", f"stash_export_u{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Type", "Category/Source", "Amount", "Description"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def export_excel(db: Session, user_id: int) -> str:
    rows = _rows(db, user_id)
    path = os.path.join(EXPORT_DIR, "excel", f"stash_export_u{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    headers = ["Date", "Type", "Category/Source", "Amount", "Description"]
    ws.append(headers)
    for r in rows:
        ws.append([r[h] for h in headers])
    for col_cells in ws.columns:
        max_len = max(len(str(c.value)) for c in col_cells if c.value is not None) if col_cells else 10
        ws.column_dimensions[col_cells[0].column_letter].width = max(10, max_len + 2)
    wb.save(path)
    return path


def export_pdf(db: Session, user_id: int) -> str:
    rows = _rows(db, user_id)
    path = os.path.join(EXPORT_DIR, "pdf", f"stash_export_u{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Stash - Transaction Export")
    y -= 30
    c.setFont("Helvetica-Bold", 9)
    headers = ["Date", "Type", "Category/Source", "Amount", "Description"]
    col_x = [40, 110, 170, 280, 340]
    for h, x in zip(headers, col_x):
        c.drawString(x, y, h)
    y -= 15
    c.setFont("Helvetica", 8)
    for r in rows:
        if y < 40:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 8)
        values = [r["Date"], r["Type"], r["Category/Source"], f"{r['Amount']:.2f}", (r["Description"] or "")[:30]]
        for v, x in zip(values, col_x):
            c.drawString(x, y, str(v))
        y -= 13
    c.save()
    return path
