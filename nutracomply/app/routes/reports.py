"""
Compliance report routes.
"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.models import ComplianceReport, LabelVersion, Product
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import can_mutate_products, can_share_reports, get_account_id
from app.services.alert_service import count_unread_alerts
from app.services.report_service import generate_pdf_html, generate_share_token, get_or_create_report

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
settings = get_settings()


def _require_user(request: Request, db: Session):
    return get_current_user_from_cookie(request, db)


def _report_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(ComplianceReport)
    if account_id:
        query = query.filter(ComplianceReport.account_id == account_id)
    else:
        query = query.filter(ComplianceReport.user_id == user.id)
    return query


@router.get("")
async def reports_list(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    reports = _report_query(db, user).order_by(ComplianceReport.created_at.desc()).all()
    for report in reports:
        _ = report.product

    return templates.TemplateResponse("reports.html", {
        "request": request,
        "user": user,
        "reports": reports,
        "unread_alerts": count_unread_alerts(db, user),
    })


@router.get("/generate/{label_version_id}")
async def generate_report(label_version_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    label_version = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
    if not label_version or not label_version.product:
        return RedirectResponse(url="/reports")

    product = label_version.product
    if product.account_id and product.account_id != get_account_id(user):
        return RedirectResponse(url="/reports")

    _ = label_version.checks
    for check in label_version.checks:
        _ = check.rule

    report = get_or_create_report(
        db,
        user.id,
        product.id,
        label_version_id,
    )
    return RedirectResponse(url=f"/reports/{report.id}", status_code=302)


@router.get("/{report_id}")
async def view_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    report = _report_query(db, user).filter(ComplianceReport.id == report_id).first()
    if not report:
        return RedirectResponse(url="/reports")

    product = report.product
    share_url = f"{settings.public_base_url.rstrip('/')}/r/{report.share_token}" if report.share_token else None
    critical_failures = sum(
        1
        for result in (report.check_results or [])
        if result.get("result") == "FAIL" and result.get("severity") == "CRITICAL"
    )

    return templates.TemplateResponse("report_detail.html", {
        "request": request,
        "user": user,
        "report": report,
        "product": product,
        "unread_alerts": count_unread_alerts(db, user),
        "just_shared": bool(request.query_params.get("shared", "")),
        "share_url": share_url,
        "critical_failures": critical_failures,
        "can_share_reports": can_share_reports(user),
        "can_promote_checker": bool(report.checker_session_id and can_mutate_products(user)),
    })


@router.get("/{report_id}/download")
async def download_report_pdf(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    report = (
        _report_query(db, user)
        .options(joinedload(ComplianceReport.user))
        .filter(ComplianceReport.id == report_id)
        .first()
    )
    if not report:
        return RedirectResponse(url="/reports")

    product = report.product
    brand_name = None
    brand_color = None
    if product and product.account_id and user.account:
        brand_name = user.account.report_brand_name or user.report_brand_name
        brand_color = user.account.report_brand_color or user.report_brand_color
    elif report.user:
        brand_name = report.user.report_brand_name
        brand_color = report.user.report_brand_color

    html_content = generate_pdf_html(report, product, brand_name=brand_name, brand_color=brand_color)
    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={report.report_ref}.pdf"},
        )
    except ImportError:
        pass

    return StreamingResponse(
        io.BytesIO(html_content.encode("utf-8")),
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename={report.report_ref}.html"},
    )


@router.post("/{report_id}/share")
async def create_share_link(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_share_reports(user):
        return RedirectResponse(url=f"/reports/{report_id}", status_code=302)

    report = _report_query(db, user).filter(ComplianceReport.id == report_id).first()
    if not report:
        return RedirectResponse(url="/reports")

    token = generate_share_token(db, report)
    share_url = f"{settings.public_base_url.rstrip('/')}/r/{token}"

    try:
        from app.services.notification import send_report_shared_email
        product_name = report.product.name if report.product else "Compliance Report"
        expires_at = report.share_expires_at.strftime("%d %b %Y") if report.share_expires_at else "30 days"
        send_report_shared_email(user, product_name, share_url, expires_at)
    except Exception:
        pass

    return RedirectResponse(url=f"/reports/{report_id}?shared=1", status_code=302)
