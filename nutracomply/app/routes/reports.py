"""
Compliance Reports Routes — generate, download, share
"""
import io
import os
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import ComplianceReport, Product, LabelVersion, Alert, AlertStatus
from app.services.report_service import get_or_create_report, generate_share_token, generate_pdf_html

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def reports_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    reports = (
        db.query(ComplianceReport)
        .filter(ComplianceReport.user_id == user.id)
        .order_by(ComplianceReport.created_at.desc())
        .all()
    )

    # Eagerly load product for each report
    for r in reports:
        _ = r.product

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("reports.html", {
        "request": request,
        "user": user,
        "reports": reports,
        "unread_alerts": unread_alerts,
    })


@router.get("/generate/{label_version_id}")
async def generate_report(label_version_id: int, request: Request, db: Session = Depends(get_db)):
    """Create or retrieve a report for a label version, then redirect to report view."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    lv = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
    if not lv:
        return RedirectResponse(url="/reports")

    # Check user owns this product
    product = db.query(Product).filter(
        Product.id == lv.product_id,
        Product.user_id == user.id
    ).first()
    if not product:
        return RedirectResponse(url="/reports")

    # Load checks eagerly
    _ = lv.checks
    for c in lv.checks:
        _ = c.rule

    report = get_or_create_report(db, user.id, product.id, label_version_id)
    return RedirectResponse(url=f"/reports/{report.id}", status_code=302)


@router.get("/{report_id}")
async def view_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    report = db.query(ComplianceReport).filter(
        ComplianceReport.id == report_id,
        ComplianceReport.user_id == user.id
    ).first()
    if not report:
        return RedirectResponse(url="/reports")

    product = report.product
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    shared = request.query_params.get("shared", "")
    token = request.query_params.get("token", "")

    return templates.TemplateResponse("report_detail.html", {
        "request": request,
        "user": user,
        "report": report,
        "product": product,
        "unread_alerts": unread_alerts,
        "just_shared": bool(shared),
        "share_url": f"{request.base_url}r/{report.share_token}" if report.share_token else None,
    })


@router.get("/{report_id}/download")
async def download_report_pdf(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    report = (
        db.query(ComplianceReport)
        .options(joinedload(ComplianceReport.user))
        .filter(
            ComplianceReport.id == report_id,
            ComplianceReport.user_id == user.id,
        )
        .first()
    )
    if not report:
        return RedirectResponse(url="/reports")

    product = report.product

    # Pass branding from the report owner's profile
    _ = report.user
    brand_name = report.user.report_brand_name if report.user else None
    brand_color = report.user.report_brand_color if report.user else None

    # Generate HTML for PDF
    html_content = generate_pdf_html(report, product, brand_name=brand_name, brand_color=brand_color)

    # Try to generate actual PDF using weasyprint if available
    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={report.report_ref}.pdf"}
        )
    except ImportError:
        pass

    # Fallback: return HTML as downloadable file
    return StreamingResponse(
        io.BytesIO(html_content.encode("utf-8")),
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename={report.report_ref}.html"}
    )


@router.post("/{report_id}/share")
async def create_share_link(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    report = db.query(ComplianceReport).filter(
        ComplianceReport.id == report_id,
        ComplianceReport.user_id == user.id
    ).first()
    if not report:
        return RedirectResponse(url="/reports")

    token = generate_share_token(db, report)
    return RedirectResponse(url=f"/reports/{report_id}?shared=1&token={token}", status_code=302)
