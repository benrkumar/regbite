"""
Settings Route — manages user profile settings, notification email addresses.
"""
import re
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import Alert, AlertStatus

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


@router.get("/settings")
async def settings_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/settings/notifications")
async def save_notification_emails(request: Request, db: Session = Depends(get_db)):
    """Save up to 5 notification email addresses for the user."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    form = await request.form()
    emails = []
    for i in range(1, 6):
        email = (form.get(f"email_{i}") or "").strip()
        if email:
            if not EMAIL_RE.match(email):
                return RedirectResponse(
                    url=f"/settings?msg=Invalid+email+format:+{email}&type=error",
                    status_code=302
                )
            emails.append(email.lower())

    # Deduplicate preserving order
    seen: set = set()
    unique_emails = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            unique_emails.append(e)

    user.notification_emails = unique_emails[:5]
    db.commit()

    return RedirectResponse(
        url="/settings?msg=Notification+emails+saved+successfully&type=success",
        status_code=302
    )
