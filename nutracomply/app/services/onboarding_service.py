from __future__ import annotations

from app.models import User
from app.services.access_control import is_platform_admin


DEMO_USER_EMAILS = {"admin", "ben", "editor", "viewer", "consultant"}
PROTECTED_APP_PREFIXES = (
    "/dashboard",
    "/products",
    "/labels",
    "/alerts",
    "/regulations",
    "/reg-alerts",
    "/renewals",
    "/reports",
    "/checker",
    "/team",
    "/billing",
    "/notifications",
    "/settings",
)
EXEMPT_PATHS = {
    "/health",
    "/billing/webhook",
}
EXEMPT_PREFIXES = (
    "/static/",
    "/uploads/",
)


def is_demo_onboarding_exempt(user: User | None, enable_demo_data: bool) -> bool:
    if not user or not enable_demo_data:
        return False
    email = (user.email or "").strip().lower()
    local_part = email.split("@", 1)[0]
    return email in DEMO_USER_EMAILS or local_part in DEMO_USER_EMAILS


def should_force_onboarding(user: User | None, path: str, enable_demo_data: bool) -> bool:
    normalized_path = path or "/"
    if not user or user.onboarding_complete:
        return False
    if is_platform_admin(user) or is_demo_onboarding_exempt(user, enable_demo_data):
        return False
    if normalized_path in EXEMPT_PATHS:
        return False
    if normalized_path.startswith(EXEMPT_PREFIXES):
        return False

    for prefix in PROTECTED_APP_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
            return True
    return False
