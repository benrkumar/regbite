"""
Settings routes for profile, notifications, passwords, branding, and API keys.
"""
from __future__ import annotations

import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import APIKey
from app.routes.auth import (
    get_current_user_from_cookie,
    hash_password,
    verify_password,
    _validate_password,
)
from app.services.access_control import (
    can_manage_api_keys,
    can_manage_branding,
    get_account_id,
)
from app.services.alert_service import count_unread_alerts

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _require_user(request: Request, db: Session):
    return get_current_user_from_cookie(request, db)


def _active_api_keys_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(APIKey).filter(APIKey.is_active == True)
    if account_id:
        query = query.filter(APIKey.account_id == account_id)
    else:
        query = query.filter(APIKey.user_id == user.id)
    return query


def _render_api_keys_page(
    request: Request,
    db: Session,
    user,
    *,
    flash_message: str | None = None,
    flash_type: str = "info",
    new_key: str | None = None,
):
    keys = _active_api_keys_query(db, user).order_by(APIKey.created_at.desc()).all()
    return templates.TemplateResponse("api_keys.html", {
        "request": request,
        "user": user,
        "keys": keys,
        "new_key": new_key,
        "unread_alerts": count_unread_alerts(db, user),
        "flash_message": flash_message or request.query_params.get("msg"),
        "flash_type": flash_type or request.query_params.get("type", "info"),
        "can_manage_api_keys": can_manage_api_keys(user),
    })


@router.get("/settings")
async def settings_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "unread_alerts": count_unread_alerts(db, user),
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
        "can_manage_branding": can_manage_branding(user),
        "can_manage_api_keys": can_manage_api_keys(user),
    })


@router.post("/settings/notifications")
async def save_notification_emails(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    emails = []
    for i in range(1, 6):
        email = (form.get(f"email_{i}") or "").strip()
        if not email:
            continue
        if not EMAIL_RE.match(email):
            return RedirectResponse(
                url=f"/settings?msg=Invalid+email+format:+{email}&type=error",
                status_code=302,
            )
        emails.append(email.lower())

    seen = set()
    unique_emails = []
    for email in emails:
        if email in seen:
            continue
        seen.add(email)
        unique_emails.append(email)

    user.notification_emails = unique_emails[:5]
    db.commit()
    return RedirectResponse(
        url="/settings?msg=Notification+emails+saved+successfully&type=success",
        status_code=302,
    )


@router.post("/settings/profile")
async def save_profile(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    user = _require_user(request, db)
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
    user = _require_user(request, db)
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

    pw_error = _validate_password(new_password)
    if pw_error:
        return RedirectResponse(
            url=f"/settings?msg={pw_error.replace(' ', '+')}&type=error",
            status_code=302,
        )

    if new_password != confirm_password:
        return RedirectResponse(
            url="/settings?msg=New+password+and+confirmation+do+not+match&type=error",
            status_code=302,
        )

    user.hashed_password = hash_password(new_password)
    db.commit()

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
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_manage_branding(user):
        return RedirectResponse(
            url="/settings?msg=Only+account+admins+can+change+branding&type=error",
            status_code=302,
        )

    form = await request.form()
    brand_name = (form.get("brand_name") or "").strip()[:255]
    brand_color = (form.get("brand_color") or "").strip()[:10]
    if brand_color and not re.match(r"^#[0-9A-Fa-f]{6}$", brand_color):
        brand_color = ""

    account = user.account
    if account:
        account.report_brand_name = brand_name or None
        account.report_brand_color = brand_color or None
    user.report_brand_name = brand_name or None
    user.report_brand_color = brand_color or None
    db.commit()

    return RedirectResponse(
        url="/settings?msg=Report+branding+saved&type=success",
        status_code=302,
    )


@router.get("/settings/api-keys")
async def api_keys_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_manage_api_keys(user):
        return templates.TemplateResponse("permission_denied.html", {
            "request": request,
            "user": user,
            "unread_alerts": count_unread_alerts(db, user),
            "denied_title": "API key access is limited to account admins",
            "denied_message": "API keys provide programmatic access to your workspace, so only account admins can view, create, or revoke them.",
            "back_url": "/settings",
            "back_label": "Back to Settings",
        }, status_code=403)
    return _render_api_keys_page(request, db, user)


@router.post("/settings/api-keys/create")
async def create_api_key(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_manage_api_keys(user):
        return _render_api_keys_page(
            request,
            db,
            user,
            flash_message="Only account admins can manage API keys.",
            flash_type="error",
        )

    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        return _render_api_keys_page(
            request,
            db,
            user,
            flash_message="Key name is required.",
            flash_type="error",
        )

    active_count = _active_api_keys_query(db, user).count()
    if active_count >= 5:
        return _render_api_keys_page(
            request,
            db,
            user,
            flash_message="Maximum 5 active API keys allowed per workspace.",
            flash_type="error",
        )

    raw_key = f"rb_live_{secrets.token_urlsafe(24)}"
    api_key = APIKey(
        account_id=get_account_id(user),
        user_id=user.id,
        name=name,
        key_prefix=raw_key[:10],
        key_hash=hash_password(raw_key),
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "api_key_created", "api_key", api_key.id, detail=f"Created API key '{name}'")
    except Exception:
        pass

    return _render_api_keys_page(
        request,
        db,
        user,
        flash_message="API key created successfully.",
        flash_type="success",
        new_key=raw_key,
    )


@router.post("/settings/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_manage_api_keys(user):
        return RedirectResponse(
            url="/settings/api-keys?msg=Only+account+admins+can+revoke+API+keys&type=error",
            status_code=302,
        )

    key = _active_api_keys_query(db, user).filter(APIKey.id == key_id).first()
    if key:
        key.is_active = False
        db.commit()

    return RedirectResponse(
        url="/settings/api-keys?msg=API+key+revoked&type=success",
        status_code=302,
    )
