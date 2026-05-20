"""
Team Management Route — invite team members, manage roles and membership.
"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie, hash_password, create_access_token
from app.models import User, UserRole, TeamInvite, Alert, AlertStatus
from app.config import get_settings
from app.utils.alerts import get_unread_alert_count

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
settings = get_settings()

# Roles that can be assigned to invited members (not super_admin / account_admin)
INVITABLE_ROLES = [UserRole.EDITOR, UserRole.VIEWER, UserRole.CONSULTANT]

ROLE_LABELS = {
    UserRole.SUPER_ADMIN:   "Super Admin",
    UserRole.ACCOUNT_ADMIN: "Account Admin",
    UserRole.EDITOR:        "Editor",
    UserRole.VIEWER:        "Viewer",
    UserRole.CONSULTANT:    "Consultant",
}


def _require_team_admin(request: Request, db: Session):
    """Return user if they're ACCOUNT_ADMIN or SUPER_ADMIN, else None."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None
    if user.role not in (UserRole.SUPER_ADMIN, UserRole.ACCOUNT_ADMIN):
        return None
    return user


# ──────────────────────────────────────────────────────────────────────────────
# GET /team
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/team")
async def team_page(request: Request, db: Session = Depends(get_db)):
    user = _require_team_admin(request, db)
    if not user:
        return RedirectResponse(url="/dashboard")

    # Team members: users whose team_id == current user's id
    members = (
        db.query(User)
        .filter(User.team_id == user.id, User.is_active == True)
        .all()
    )

    # Pending (non-accepted, non-expired) invites created by current user
    now = datetime.utcnow()
    pending_invites = (
        db.query(TeamInvite)
        .filter(
            TeamInvite.invited_by == user.id,
            TeamInvite.is_accepted == False,
            TeamInvite.expires_at > now,
        )
        .order_by(TeamInvite.created_at.desc())
        .all()
    )

    unread_alerts = get_unread_alert_count(user, db)

    return templates.TemplateResponse("team.html", {
        "request": request,
        "user": user,
        "members": members,
        "pending_invites": pending_invites,
        "invitable_roles": INVITABLE_ROLES,
        "role_labels": ROLE_LABELS,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


# ──────────────────────────────────────────────────────────────────────────────
# POST /team/invite
# ──────────────────────────────────────────────────────────────────────────────

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

    # Validate role
    try:
        invite_role = UserRole(role)
        if invite_role not in INVITABLE_ROLES:
            raise ValueError("invalid role")
    except ValueError:
        return RedirectResponse(
            url="/team?msg=Invalid+role+selected&type=error",
            status_code=302,
        )

    # Check if email already has an account
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse(
            url=f"/team?msg=An+account+with+{email}+already+exists&type=error",
            status_code=302,
        )

    # Check for an active (non-accepted, non-expired) invite to the same email
    now = datetime.utcnow()
    active_invite = db.query(TeamInvite).filter(
        TeamInvite.email == email,
        TeamInvite.invited_by == user.id,
        TeamInvite.is_accepted == False,
        TeamInvite.expires_at > now,
    ).first()
    if active_invite:
        link = f"/team/accept/{active_invite.token}"
        return RedirectResponse(
            url=f"/team?msg=An+invite+for+{email}+is+already+pending.+Link:+{link}&type=info",
            status_code=302,
        )

    token = secrets.token_urlsafe(32)
    invite = TeamInvite(
        email=email,
        role=invite_role,
        invited_by=user.id,
        token=token,
        is_accepted=False,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db.add(invite)
    db.commit()

    link = f"/team/accept/{token}"

    # Send invite email
    try:
        from app.services.notification import send_team_invite_email
        base_url = str(request.base_url).rstrip("/")
        invite_url = f"{base_url}{link}"
        send_team_invite_email(email, user.name, invite_role.value, invite_url)
    except Exception:
        pass

    msg = f"Invite+sent+to+{email}!+Link:+{link}"
    return RedirectResponse(
        url=f"/team?msg={msg}&type=success",
        status_code=302,
    )


# ──────────────────────────────────────────────────────────────────────────────
# POST /team/members/{user_id}/role
# ──────────────────────────────────────────────────────────────────────────────

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

    member = db.query(User).filter(
        User.id == user_id,
        User.team_id == current_user.id,
    ).first()
    if not member:
        return RedirectResponse(
            url="/team?msg=Team+member+not+found&type=error",
            status_code=302,
        )

    try:
        new_role = UserRole(role)
        if new_role not in INVITABLE_ROLES:
            raise ValueError("invalid role")
    except ValueError:
        return RedirectResponse(
            url="/team?msg=Invalid+role+selected&type=error",
            status_code=302,
        )

    member.role = new_role
    db.commit()

    return RedirectResponse(
        url="/team?msg=Role+updated+successfully&type=success",
        status_code=302,
    )


# ──────────────────────────────────────────────────────────────────────────────
# POST /team/members/{user_id}/remove
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/team/members/{user_id}/remove")
async def remove_member(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = _require_team_admin(request, db)
    if not current_user:
        return RedirectResponse(url="/dashboard")

    member = db.query(User).filter(
        User.id == user_id,
        User.team_id == current_user.id,
    ).first()
    if not member:
        return RedirectResponse(
            url="/team?msg=Team+member+not+found&type=error",
            status_code=302,
        )

    member.is_active = False
    db.commit()

    return RedirectResponse(
        url="/team?msg=Team+member+removed&type=success",
        status_code=302,
    )


# ──────────────────────────────────────────────────────────────────────────────
# POST /team/invites/{invite_id}/revoke
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/team/invites/{invite_id}/revoke")
async def revoke_invite(
    invite_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = _require_team_admin(request, db)
    if not current_user:
        return RedirectResponse(url="/dashboard")

    invite = db.query(TeamInvite).filter(
        TeamInvite.id == invite_id,
        TeamInvite.invited_by == current_user.id,
    ).first()
    if not invite:
        return RedirectResponse(
            url="/team?msg=Invite+not+found&type=error",
            status_code=302,
        )

    db.delete(invite)
    db.commit()

    return RedirectResponse(
        url="/team?msg=Invite+revoked&type=success",
        status_code=302,
    )


# ──────────────────────────────────────────────────────────────────────────────
# GET /team/accept/{token}
# ──────────────────────────────────────────────────────────────────────────────

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
            "error": "This invite link has expired. Please ask your team admin to send a new invite.",
            "invite": None,
        })

    # Load inviter name
    inviter = db.query(User).filter(User.id == invite.invited_by).first()

    return templates.TemplateResponse("team_accept.html", {
        "request": request,
        "invite": invite,
        "inviter": inviter,
        "role_label": ROLE_LABELS.get(invite.role, invite.role.value),
        "error": None,
    })


# ──────────────────────────────────────────────────────────────────────────────
# POST /team/accept/{token}
# ──────────────────────────────────────────────────────────────────────────────

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

    def _error(msg: str):
        inviter = db.query(User).filter(User.id == invite.invited_by).first() if invite else None
        return templates.TemplateResponse("team_accept.html", {
            "request": request,
            "invite": invite,
            "inviter": inviter,
            "role_label": ROLE_LABELS.get(invite.role, invite.role.value) if invite else "",
            "error": msg,
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

    from app.utils.password import validate_password
    pw_error = validate_password(password)
    if pw_error:
        return _error(pw_error)

    if password != confirm_password:
        return _error("Passwords do not match.")

    # Check if email was already registered (race condition guard)
    existing = db.query(User).filter(User.email == invite.email).first()
    if existing:
        return _error("An account with this email already exists. Please sign in.")

    # Create the new user
    new_user = User(
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

    # Mark invite as accepted
    invite.is_accepted = True
    db.commit()
    db.refresh(new_user)

    # Send welcome notifications
    try:
        from app.services.notify_service import push
        push(new_user.id, "Welcome to RegBite!",
             "Your account has been created. Start by adding your first product.",
             ntype="success", link="/products")
        # Also notify the inviter
        push(invite.invited_by, f"{name} accepted your invite",
             f"{invite.email} has joined your team.", ntype="info", link="/team")
    except Exception:
        pass

    # Send invite-accepted email to inviter
    try:
        from app.services.notification import send_invite_accepted_email
        inviter = db.query(User).filter(User.id == invite.invited_by).first()
        send_invite_accepted_email(inviter, name, invite.email, invite.role.value)
    except Exception:
        pass

    # Log them in immediately
    token_val = create_access_token({"sub": new_user.email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        "access_token",
        token_val,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
    )
    return response
