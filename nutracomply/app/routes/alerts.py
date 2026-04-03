from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import Alert, AlertStatus
from app.routes.auth import get_current_user_from_cookie

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
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(100)
        .all()
    )
    for a in alerts:
        _ = a.product

    unread_count = sum(1 for a in alerts if a.status == AlertStatus.UNREAD)

    return templates.TemplateResponse("alerts.html", {
        "request": request,
        "user": user,
        "alerts": alerts,
        "unread_alerts": unread_count,
        "AlertStatus": AlertStatus,
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

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        try:
            alert.status = AlertStatus(status)
            if status == AlertStatus.RESOLVED.value:
                from datetime import datetime
                alert.resolved_at = datetime.utcnow()
            db.commit()
        except ValueError:
            pass

    return RedirectResponse(url="/alerts", status_code=302)


@router.post("/alerts/mark-all-read")
async def mark_all_read(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).update(
        {"status": AlertStatus.ACKNOWLEDGED}
    )
    db.commit()
    return RedirectResponse(url="/alerts", status_code=302)
