"""
Settings Route — manages user profile settings, notification email addresses,
profile name updates, and password changes.
"""
import re
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie, hash_password, verify_password
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


@router.post("/settings/profile")
async def save_profile(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    """Update the user's display name."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    name = name.strip()
    if len(name) < 2:
        return RedirectResponse(
            url="/settings?msg=Name+must+be+at+least+2+characters&type=error",
            status_code=302,
        )
    if len(name) > 100:
        return RedirectResponse(
            url="/settings?msg=Name+must+be+100+characters+or+fewer&type=error",
            status_code=302,
        )

    user.name = name
    db.commit()

    return RedirectResponse(
        url="/settings?msg=Profile+updated+successfully&type=success",
        status_code=302,
    )


@router.post("/settings/password")
async def change_password(
    request: Request,
    db: Session = Depends(get_db),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Change the user's password after verifying the current one."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    if not verify_password(current_password, user.hashed_password):
        return RedirectResponse(
            url="/settings?msg=Current+password+is+incorrect&type=error",
            status_code=302,
        )

    if new_password == current_password:
        return RedirectResponse(
            url="/settings?msg=New+password+must+be+different+from+current+password&type=error",
            status_code=302,
        )

    if len(new_password) < 8:
        return RedirectResponse(
            url="/settings?msg=New+password+must+be+at+least+8+characters&type=error",
            status_code=302,
        )

    if new_password != confirm_password:
        return RedirectResponse(
            url="/settings?msg=New+password+and+confirmation+do+not+match&type=error",
            status_code=302,
        )

    user.hashed_password = hash_password(new_password)
    db.commit()

    return RedirectResponse(
        url="/settings?msg=Password+updated+successfully&type=success",
        status_code=302,
    )
