"""
Help & Documentation Routes — role-filtered in-portal docs and FAQ.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import Alert, AlertStatus

router = APIRouter(prefix="/help")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# ── Section metadata ─────────────────────────────────────────────────────────

SECTIONS = [
    {"slug": "getting-started", "label": "Getting Started", "icon": "→",
     "desc": "Platform overview and first steps"},
    {"slug": "products", "label": "Products", "icon": "□",
     "desc": "Create products and upload label images"},
    {"slug": "compliance", "label": "Compliance Engine", "icon": "◇",
     "desc": "Comprehensive checks across 5 regulatory frameworks"},
    {"slug": "reports", "label": "Reports", "icon": "▤",
     "desc": "Generate, download, and share compliance reports"},
    {"slug": "regulations", "label": "Regulations", "icon": "≡",
     "desc": "Track regulation changes and alerts"},
    {"slug": "licenses", "label": "License Renewals", "icon": "○",
     "desc": "Track license expiry and renewals"},
    {"slug": "team", "label": "Team Management", "icon": "⊞",
     "desc": "Invite members and manage roles"},
    {"slug": "billing", "label": "Billing & Plans", "icon": "◻",
     "desc": "Plans, quotas, and payments"},
    {"slug": "settings", "label": "Settings", "icon": "◈",
     "desc": "Profile, passwords, API keys, branding"},
    {"slug": "admin", "label": "Admin Panel", "icon": "▣",
     "desc": "User management, rules, LLM KB, system controls"},
]

# Role → accessible section slugs
ROLE_SECTIONS: dict[str, list[str]] = {
    "super_admin": [s["slug"] for s in SECTIONS],
    "account_admin": [s["slug"] for s in SECTIONS if s["slug"] != "admin"],
    "editor": [
        "getting-started", "products", "compliance", "reports",
        "regulations", "licenses", "settings",
    ],
    "viewer": [
        "getting-started", "products", "compliance", "reports", "regulations",
    ],
    "consultant": [
        "getting-started", "compliance", "reports", "regulations",
    ],
}

# FAQ categories → accessible roles
FAQ_CATEGORIES: dict[str, list[str]] = {
    "general": ["super_admin", "account_admin", "editor", "viewer", "consultant"],
    "label_analysis": ["super_admin", "account_admin", "editor", "viewer"],
    "compliance_rules": ["super_admin", "account_admin", "editor", "viewer", "consultant"],
    "reports": ["super_admin", "account_admin", "editor", "viewer", "consultant"],
    "team_roles": ["super_admin", "account_admin"],
    "billing": ["super_admin", "account_admin"],
    "account": ["super_admin", "account_admin", "editor"],
    "admin": ["super_admin"],
}


def _get_user_sections(role_value: str) -> list[dict]:
    """Return section metadata list filtered for a given role."""
    allowed = ROLE_SECTIONS.get(role_value, ROLE_SECTIONS["account_admin"])
    return [s for s in SECTIONS if s["slug"] in allowed]


def _get_user_faq_categories(role_value: str) -> list[str]:
    """Return FAQ category keys accessible to a given role."""
    return [cat for cat, roles in FAQ_CATEGORIES.items() if role_value in roles]


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def help_hub(request: Request, db: Session = Depends(get_db)):
    """Documentation index — cards linking to each section."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    role = user.role.value if user.role else "account_admin"
    sections = _get_user_sections(role)
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("help/hub.html", {
        "request": request,
        "user": user,
        "sections": sections,
        "unread_alerts": unread_alerts,
    })


@router.get("/faq")
async def help_faq(request: Request, db: Session = Depends(get_db)):
    """FAQ page with role-filtered accordion categories."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    role = user.role.value if user.role else "account_admin"
    sections = _get_user_sections(role)
    faq_categories = _get_user_faq_categories(role)
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("help/faq.html", {
        "request": request,
        "user": user,
        "sections": sections,
        "faq_categories": faq_categories,
        "active_section": "faq",
        "unread_alerts": unread_alerts,
    })


@router.get("/{section}")
async def help_section(section: str, request: Request, db: Session = Depends(get_db)):
    """Render a specific documentation section if the user's role allows it."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    role = user.role.value if user.role else "account_admin"
    allowed = ROLE_SECTIONS.get(role, ROLE_SECTIONS["account_admin"])

    if section not in allowed:
        return RedirectResponse(url="/help")

    sections = _get_user_sections(role)
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    # Map slug to template filename (hyphens → underscores)
    template_name = f"help/{section.replace('-', '_')}.html"

    return templates.TemplateResponse(template_name, {
        "request": request,
        "user": user,
        "sections": sections,
        "active_section": section,
        "unread_alerts": unread_alerts,
    })
