"""
Team management routes for shared workspace membership.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import TeamInvite, User, UserRole
from app.routes.auth import (
    _validate_password,
    create_access_token,
    get_current_user_from_cookie,
    hash_password,
)
from app.services.access_control import (
    can_manage_team,
    ensure_workspace_for_user,
    get_account_id,
    sync_user_role_flags,
)
from app.services.alert_service import count_unread_alerts

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
settings = get_settings()

INVITABLE_ROLES = [UserRole.EDITOR, UserRole.VIEWER, UserRole.CONSULTANT]

ROLE_LABELS = {
    UserRole.SUPER_ADMIN: "Super Admin",
    UserRole.ACCOUNT_ADMIN: "Account Admin",
    UserRole.EDITOR: "Editor",
    UserRole.VIEWER: "Viewer",
    UserRole.CONSULTANT: "Consultant",
}


def _require_team_admin(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user or not can_manage_team(user):
        return None
    return user


def _workspace_members_query(db: Session, user):
    account_id = get_account_id(user)
    return db.query(User).filter(User.account_id == account_id, User.is_active == True)


@router.get("/team")
async def team_page(request: Request, db: Session = Depends(get_db)):
    user = _require_team_admin(request, db)
    if not user:
        return RedirectResponse(url="/dashboard")

    members = _workspace_members_query(db, user).order_by(User.created_at.asc()).all()
    now = datetime.utcnow()
    pending_invites = (
        db.query(TeamInvite)
        .filter(
            TeamInvite.account_id == get_account_id(user),
            TeamInvite.is_accepted == False,
            TeamInvite.expires_at > now,
        )
        .order_by(TeamInvite.created_at.desc())
        .all()
    )

    return templates.TemplateResponse("team.html", {
        "request": request,
        "user": user,
        "members": members,
        "pending_invites": pending_invites,
        "invitable_roles": INVITABLE_ROLES,
        "role_labels": ROLE_LABELS,
        "unread_alerts": count_unread_alerts(db, user),
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/team/invite")
async def create_invite(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    role: str = Form(...),
):
    user = _require_team_admin(request, db)
    if not user:
        return RedirectResponse(url="/dashboard")

    email = email.lower().strip()
    try:
        invite_role = UserRole(role)
        if invite_role not in INVITABLE_ROLES:
            raise ValueError("invalid role")
    except ValueError:
        return RedirectResponse(
            url="/team?msg=Invalid+role+selected&type=error",
            status_code=302,
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if existing.account_id == get_account_id(user):
            msg = f"{email}+is+already+in+this+workspace"
        else:
            msg = f"An+account+with+{email}+already+exists"
        return RedirectResponse(url=f"/team?msg={msg}&type=error", status_code=302)

    now = datetime.utcnow()
    active_invite = (
        db.query(TeamInvite)
        .filter(
            TeamInvite.email == email,
            TeamInvite.account_id == get_account_id(user),
            TeamInvite.is_accepted == False,
            TeamInvite.expires_at > now,
        )
        .first()
    )
    if active_invite:
        link = f"/team/accept/{active_invite.token}"
        return RedirectResponse(
            url=f"/team?msg=An+invite+for+{email}+is+already+pending.+Link:+{link}&type=info",
            status_code=302,
        )

    invite = TeamInvite(
        account_id=get_account_id(user),
        email=email,
        role=invite_role,
        invited_by=user.id,
        token=secrets.token_urlsafe(32),
        is_accepted=False,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db.add(invite)
    db.commit()

    invite_url = f"{settings.public_base_url.rstrip('/')}/team/accept/{invite.token}"
    try:
        from app.services.notification import send_team_invite_email
        send_team_invite_email(email, user.name, invite_role.value, invite_url)
    except Exception:
        pass

    msg = f"Invite+sent+to+{email}"
    return RedirectResponse(url=f"/team?msg={msg}&type=success", status_code=302)


@router.post("/team/members/{user_id}/role")
async def update_member_role(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    role: str = Form(...),
):
    current_user = _require_team_admin(request, db)
    if not current_user:
        return RedirectResponse(url="/dashboard")

    member = _workspace_members_query(db, current_user).filter(User.id == user_id).first()
    if not member or member.id == current_user.id:
        return RedirectResponse(url="/team?msg=Team+member+not+found&type=error", status_code=302)

    try:
        new_role = UserRole(role)
        if new_role not in INVITABLE_ROLES:
            raise ValueError("invalid role")
    except ValueError:
        return RedirectResponse(url="/team?msg=Invalid+role+selected&type=error", status_code=302)

    member.role = new_role
    sync_user_role_flags(member)
    db.commit()
    return RedirectResponse(url="/team?msg=Role+updated+successfully&type=success", status_code=302)


@router.post("/team/members/{user_id}/remove")
async def remove_member(user_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = _require_team_admin(request, db)
    if not current_user:
        return RedirectResponse(url="/dashboard")

    member = _workspace_members_query(db, current_user).filter(User.id == user_id).first()
    if not member or member.id == current_user.id:
        return RedirectResponse(url="/team?msg=Team+member+not+found&type=error", status_code=302)

    member.is_active = False
    db.commit()
    return RedirectResponse(url="/team?msg=Team+member+removed&type=success", status_code=302)


@router.post("/team/invites/{invite_id}/revoke")
async def revoke_invite(invite_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = _require_team_admin(request, db)
    if not current_user:
        return RedirectResponse(url="/dashboard")

    invite = (
        db.query(TeamInvite)
        .filter(
            TeamInvite.id == invite_id,
            TeamInvite.account_id == get_account_id(current_user),
        )
        .first()
    )
    if not invite:
        return RedirectResponse(url="/team?msg=Invite+not+found&type=error", status_code=302)

    db.delete(invite)
    db.commit()
    return RedirectResponse(url="/team?msg=Invite+revoked&type=success", status_code=302)


@router.get("/team/accept/{token}")
async def accept_invite_page(token: str, request: Request, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    invite = db.query(TeamInvite).filter(TeamInvite.token == token).first()
    if not invite:
        return templates.TemplateResponse("team_accept.html", {
            "request": request,
            "error": "This invite link is invalid or has already been used.",
            "invite": None,
        })
    if invite.is_accepted:
        return templates.TemplateResponse("team_accept.html", {
            "request": request,
            "error": "This invite has already been accepted. Please log in.",
            "invite": None,
        })
    if invite.expires_at < now:
        return templates.TemplateResponse("team_accept.html", {
            "request": request,
            "error": "This invite link has expired. Please ask your workspace admin to send a new invite.",
            "invite": None,
        })

    inviter = db.query(User).filter(User.id == invite.invited_by).first()
    return templates.TemplateResponse("team_accept.html", {
        "request": request,
        "invite": invite,
        "inviter": inviter,
        "role_label": ROLE_LABELS.get(invite.role, invite.role.value),
        "error": None,
    })


@router.post("/team/accept/{token}")
async def process_invite_accept(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    now = datetime.utcnow()
    invite = db.query(TeamInvite).filter(TeamInvite.token == token).first()

    def _error(message: str):
        inviter = db.query(User).filter(User.id == invite.invited_by).first() if invite else None
        return templates.TemplateResponse("team_accept.html", {
            "request": request,
            "invite": invite,
            "inviter": inviter,
            "role_label": ROLE_LABELS.get(invite.role, invite.role.value) if invite else "",
            "error": message,
        })

    if not invite or invite.is_accepted or invite.expires_at < now:
        return templates.TemplateResponse("team_accept.html", {
            "request": request,
            "error": "This invite link is invalid, expired, or already used.",
            "invite": None,
        })

    name = name.strip()
    if len(name) < 2:
        return _error("Name must be at least 2 characters.")

    pw_error = _validate_password(password)
    if pw_error:
        return _error(pw_error)

    if password != confirm_password:
        return _error("Passwords do not match.")

    existing = db.query(User).filter(User.email == invite.email).first()
    if existing:
        return _error("An account with this email already exists. Please sign in.")

    new_user = User(
        account_id=invite.account_id,
        name=name,
        email=invite.email,
        hashed_password=hash_password(password),
        is_admin=False,
        role=invite.role,
        is_active=True,
        notification_emails=[],
        team_id=invite.invited_by,
    )
    db.add(new_user)
    sync_user_role_flags(new_user)
    invite.is_accepted = True
    ensure_workspace_for_user(db, new_user)
    db.commit()
    db.refresh(new_user)

    try:
        from app.services.notify_service import push
        push(new_user.id, "Welcome to RegBite!", "Your account has been created. Start by adding your first product.", ntype="success", link="/products")
        push(invite.invited_by, f"{name} accepted your invite", f"{invite.email} has joined your workspace.", ntype="info", link="/team")
    except Exception:
        pass

    try:
        from app.services.notification import send_invite_accepted_email
        inviter = db.query(User).filter(User.id == invite.invited_by).first()
        send_invite_accepted_email(inviter, name, invite.email, invite.role.value)
    except Exception:
        pass

    token_val = create_access_token({"sub": new_user.email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        "access_token",
        token_val,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
    )
    return response
