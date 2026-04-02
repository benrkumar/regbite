"""
Quota enforcement service.
Checks user's current plan limits and returns whether an action is allowed.
"""
from app.database import SessionLocal
from app.services.billing_service import PLANS


def get_user_plan(user) -> str:
    """Return plan string for user: 'free', 'growth', or 'enterprise'."""
    try:
        if user.plan:
            return user.plan.value if hasattr(user.plan, 'value') else str(user.plan)
    except Exception:
        pass
    return "free"


def check_product_limit(user, db) -> tuple:
    """
    Returns (allowed: bool, message: str).
    Checks if user can create another product under their plan.
    Admin users always bypass limits.
    """
    # Admin users have unlimited access
    if getattr(user, 'is_admin', False):
        return True, ""

    plan_key = get_user_plan(user)
    limits = PLANS.get(plan_key, PLANS["free"])
    max_products = limits.get("product_limit")

    if max_products is None:  # unlimited (enterprise)
        return True, ""

    from app.models import Product
    current_count = db.query(Product).filter(
        Product.user_id == user.id,
        Product.is_active == True
    ).count()

    if current_count >= max_products:
        return False, (
            f"Your {limits['name']} plan allows up to {max_products} products. "
            f"You currently have {current_count}. "
            "Upgrade to Growth for up to 25 products."
        )
    return True, ""


def check_scan_limit(user, db) -> tuple:
    """
    Returns (allowed: bool, message: str).
    Checks monthly label scan usage against plan limit.
    Monthly scans = LabelVersion rows created this calendar month by this user.
    Admin users always bypass limits.
    """
    # Admin users have unlimited access
    if getattr(user, 'is_admin', False):
        return True, ""

    plan_key = get_user_plan(user)
    limits = PLANS.get(plan_key, PLANS["free"])
    max_scans = limits.get("scan_limit_monthly")

    if max_scans is None:  # unlimited
        return True, ""

    from datetime import datetime
    from app.models import LabelVersion, Product

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    scans_this_month = (
        db.query(LabelVersion)
        .join(Product, LabelVersion.product_id == Product.id)
        .filter(
            Product.user_id == user.id,
            LabelVersion.uploaded_at >= month_start,
        )
        .count()
    )

    if scans_this_month >= max_scans:
        return False, (
            f"Your {limits['name']} plan allows {max_scans} scans per month. "
            f"You've used {scans_this_month} this month. "
            "Upgrade to Growth for 100 scans/month."
        )
    return True, ""
