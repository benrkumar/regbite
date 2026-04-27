from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, AlertStatus
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import can_edit_account_data
from app.services.alert_service import (
    account_alert_query,
    attach_read_state,
    count_unread_alerts,
    mark_alert_read,
    mark_all_alerts_read,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def require_user(request: Request, db: Session):
    return get_current_user_from_cookie(request, db)


@router.get("/alerts")
async def alerts_list(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    alerts = (
        account_alert_query(db, user)
        .order_by(Alert.created_at.desc())
        .limit(100)
        .all()
    )
    for alert in alerts:
        _ = alert.product
    attach_read_state(db, user, alerts)
    unread_count = sum(1 for alert in alerts if getattr(alert, "is_unread", False))

    return templates.TemplateResponse("alerts.html", {
        "request": request,
        "user": user,
        "alerts": alerts,
        "unread_alerts": unread_count,
        "AlertStatus": AlertStatus,
        "can_update_alerts": can_edit_account_data(user),
    })


@router.post("/alerts/{alert_id}/status")
async def update_alert_status(
    alert_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_edit_account_data(user):
        return RedirectResponse(url="/alerts", status_code=302)

    alert = account_alert_query(db, user).filter(Alert.id == alert_id).first()
    if alert:
        try:
            alert.status = AlertStatus(status)
            if alert.status == AlertStatus.RESOLVED:
                alert.resolved_at = datetime.utcnow()
            mark_alert_read(db, user, alert)
            db.commit()
        except ValueError:
            db.rollback()

    return RedirectResponse(url="/alerts", status_code=302)


@router.post("/alerts/mark-all-read")
async def mark_all_read(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    mark_all_alerts_read(db, user)
    db.commit()
    return RedirectResponse(url="/alerts", status_code=302)
