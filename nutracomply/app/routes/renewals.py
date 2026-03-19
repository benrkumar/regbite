"""
License Renewal Tracker Routes
"""
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import LicenseRenewal, LicenseType, Alert, AlertStatus

router = APIRouter(prefix="/renewals")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def renewals_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    licenses = (
        db.query(LicenseRenewal)
        .filter(LicenseRenewal.user_id == user.id, LicenseRenewal.is_active == True)
        .order_by(LicenseRenewal.expiry_date.asc())
        .all()
    )

    # Count by status
    expired = [l for l in licenses if l.days_until_expiry < 0]
    expiring_soon = [l for l in licenses if 0 <= l.days_until_expiry <= 30]
    expiring_60 = [l for l in licenses if 30 < l.days_until_expiry <= 60]
    active = [l for l in licenses if l.days_until_expiry > 60]

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("renewals.html", {
        "request": request,
        "user": user,
        "licenses": licenses,
        "expired": expired,
        "expiring_soon": expiring_soon,
        "expiring_60": expiring_60,
        "active": active,
        "license_types": [lt.value for lt in LicenseType],
        "unread_alerts": unread_alerts,
    })


@router.post("/add")
async def add_renewal(
    request: Request,
    license_name: str = Form(...),
    license_type: str = Form(...),
    license_number: str = Form(""),
    expiry_date: str = Form(...),
    issued_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    try:
        expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d")
        issued_dt = datetime.strptime(issued_date, "%Y-%m-%d") if issued_date else None

        license = LicenseRenewal(
            user_id=user.id,
            license_name=license_name,
            license_type=LicenseType(license_type),
            license_number=license_number or None,
            expiry_date=expiry_dt,
            issued_date=issued_dt,
            notes=notes or None,
        )
        db.add(license)
        db.commit()
    except Exception as e:
        print(f"[renewals] Error adding license: {e}")

    return RedirectResponse(url="/renewals", status_code=302)


@router.post("/{license_id}/delete")
async def delete_renewal(license_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    license = db.query(LicenseRenewal).filter(
        LicenseRenewal.id == license_id,
        LicenseRenewal.user_id == user.id
    ).first()
    if license:
        license.is_active = False
        db.commit()

    return RedirectResponse(url="/renewals", status_code=302)


@router.post("/{license_id}/renew")
async def renew_license(
    license_id: int,
    request: Request,
    new_expiry_date: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    license = db.query(LicenseRenewal).filter(
        LicenseRenewal.id == license_id,
        LicenseRenewal.user_id == user.id
    ).first()
    if license:
        try:
            new_dt = datetime.strptime(new_expiry_date, "%Y-%m-%d")
            license.expiry_date = new_dt
            license.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            print(f"[renewals] Error renewing: {e}")

    return RedirectResponse(url="/renewals", status_code=302)
