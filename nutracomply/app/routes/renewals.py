"""
License renewal tracker routes.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LicenseRenewal, LicenseType
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import get_account_id
from app.services.alert_service import count_unread_alerts

router = APIRouter(prefix="/renewals")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_user(request: Request, db: Session):
    return get_current_user_from_cookie(request, db)


def _renewal_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(LicenseRenewal).filter(LicenseRenewal.is_active == True)
    if account_id:
        query = query.filter(LicenseRenewal.account_id == account_id)
    else:
        query = query.filter(LicenseRenewal.user_id == user.id)
    return query


@router.get("")
async def renewals_list(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    licenses = _renewal_query(db, user).order_by(LicenseRenewal.expiry_date.asc()).all()
    perpetual = [item for item in licenses if item.is_perpetual]
    non_perpetual = [item for item in licenses if not item.is_perpetual]
    expired = [item for item in non_perpetual if item.days_until_expiry < 0]
    expiring_soon = [item for item in non_perpetual if 0 <= item.days_until_expiry <= 30]
    expiring_60 = [item for item in non_perpetual if 30 < item.days_until_expiry <= 60]
    active = [item for item in non_perpetual if item.days_until_expiry > 60] + perpetual

    return templates.TemplateResponse("renewals.html", {
        "request": request,
        "user": user,
        "licenses": licenses,
        "expired": expired,
        "expiring_soon": expiring_soon,
        "expiring_60": expiring_60,
        "active": active,
        "perpetual": perpetual,
        "license_types": [item.value for item in LicenseType],
        "unread_alerts": count_unread_alerts(db, user),
        "perpetual_notice": "FSSAI licenses issued after March 2026 have perpetual validity under the Licensing & Registration Amendment Regulations 2026. No renewal is required.",
    })


@router.post("/add")
async def add_renewal(
    request: Request,
    license_name: str = Form(...),
    license_type: str = Form(...),
    license_number: str = Form(""),
    expiry_date: str = Form(""),
    issued_date: str = Form(""),
    is_perpetual: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    try:
        perpetual = is_perpetual.lower() in ("true", "1", "on", "yes") if is_perpetual else False
        expiry_dt = datetime(2099, 12, 31) if perpetual else datetime.strptime(expiry_date, "%Y-%m-%d")
        issued_dt = datetime.strptime(issued_date, "%Y-%m-%d") if issued_date else None

        renewal = LicenseRenewal(
            account_id=get_account_id(user),
            user_id=user.id,
            license_name=license_name,
            license_type=LicenseType(license_type),
            license_number=license_number or None,
            expiry_date=expiry_dt,
            issued_date=issued_dt,
            is_perpetual=perpetual,
            notes=notes or None,
        )
        db.add(renewal)
        db.commit()
    except Exception as exc:
        print(f"[renewals] Error adding license: {exc}")

    return RedirectResponse(url="/renewals", status_code=302)


@router.post("/{license_id}/delete")
async def delete_renewal(license_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    renewal = _renewal_query(db, user).filter(LicenseRenewal.id == license_id).first()
    if renewal:
        renewal.is_active = False
        db.commit()
    return RedirectResponse(url="/renewals", status_code=302)


@router.post("/{license_id}/renew")
async def renew_license(
    license_id: int,
    request: Request,
    new_expiry_date: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    renewal = _renewal_query(db, user).filter(LicenseRenewal.id == license_id).first()
    if renewal:
        try:
            renewal.expiry_date = datetime.strptime(new_expiry_date, "%Y-%m-%d")
            renewal.updated_at = datetime.utcnow()
            renewal.is_perpetual = False
            db.commit()
        except Exception as exc:
            print(f"[renewals] Error renewing: {exc}")

    return RedirectResponse(url="/renewals", status_code=302)
