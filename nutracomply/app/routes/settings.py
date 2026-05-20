"""
Settings Route — manages user profile settings, notification email addresses,
profile name updates, and password changes.
"""
import re
import secrets
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie, hash_password, verify_password
from app.models import Alert, AlertStatus, APIKey
from app.utils.alerts import get_unread_alert_count

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


@router.get("/settings")
async def settings_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    unread_alerts = get_unread_alert_count(user, db)

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
        return RedirectResponse(url="/login", status_code=302)

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
        return RedirectResponse(url="/login", status_code=302)

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
        return RedirectResponse(url="/login", status_code=302)

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

    from app.utils.password import validate_password
    pw_error = validate_password(new_password)
    if pw_error:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/settings?msg={quote(pw_error)}&type=error",
            status_code=302,
        )

    if new_password != confirm_password:
        return RedirectResponse(
            url="/settings?msg=New+password+and+confirmation+do+not+match&type=error",
            status_code=302,
        )

    user.hashed_password = hash_password(new_password)
    db.commit()

    # Send password changed notification email
    try:
        from app.services.notification import send_password_changed_email
        send_password_changed_email(user)
    except Exception:
        pass

    return RedirectResponse(
        url="/settings?msg=Password+updated+successfully&type=success",
        status_code=302,
    )


@router.post("/settings/branding")
async def save_branding(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    form = await request.form()
    brand_name = (form.get("brand_name") or "").strip()[:255]
    brand_color = (form.get("brand_color") or "").strip()[:10]
    # Validate hex color
    import re
    if brand_color and not re.match(r'^#[0-9A-Fa-f]{6}$', brand_color):
        brand_color = ""
    user.report_brand_name = brand_name or None
    user.report_brand_color = brand_color or None
    db.commit()
    return RedirectResponse(url="/settings?msg=Report+branding+saved&type=success", status_code=302)


# ── API Keys ──────────────────────────────────────────────────────────────────

@router.get("/settings/api-keys")
async def api_keys_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    keys = db.query(APIKey).filter(APIKey.user_id == user.id, APIKey.is_active == True).order_by(APIKey.created_at.desc()).all()
    unread_alerts = get_unread_alert_count(user, db)
    new_key = request.query_params.get("new_key")  # shown once after creation
    return templates.TemplateResponse("api_keys.html", {
        "request": request,
        "user": user,
        "keys": keys,
        "new_key": new_key,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/settings/api-keys/create")
async def create_api_key(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        return RedirectResponse(url="/settings/api-keys?msg=Key+name+is+required&type=error", status_code=302)

    # Check limit: max 5 active keys
    active_count = db.query(APIKey).filter(APIKey.user_id == user.id, APIKey.is_active == True).count()
    if active_count >= 5:
        return RedirectResponse(url="/settings/api-keys?msg=Maximum+5+API+keys+allowed&type=error", status_code=302)

    # Generate key: rb_live_{32 random chars}
    raw_key = f"rb_live_{secrets.token_urlsafe(24)}"
    key_prefix = raw_key[:10]

    # Hash the key (use passlib bcrypt same as passwords)
    key_hash = hash_password(raw_key)

    api_key = APIKey(
        user_id=user.id,
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "api_key_created", "api_key", api_key.id, detail=f"Created API key '{name}'")
    except Exception:
        pass

    # Return the template directly — NEVER put the raw secret in the URL
    keys = db.query(APIKey).filter(APIKey.user_id == user.id, APIKey.is_active == True).order_by(APIKey.created_at.desc()).all()
    unread_alerts = get_unread_alert_count(user, db)
    return templates.TemplateResponse("api_keys.html", {
        "request": request,
        "user": user,
        "keys": keys,
        "new_key": raw_key,  # shown once in the one-time banner, never in the URL
        "unread_alerts": unread_alerts,
        "flash_message": "API key created — copy it now, it won't be shown again.",
        "flash_type": "success",
    })


@router.post("/settings/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.user_id == user.id).first()
    if key:
        key.is_active = False
        db.commit()

    return RedirectResponse(url="/settings/api-keys?msg=API+key+revoked&type=success", status_code=302)
