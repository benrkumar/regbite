"""
Quota enforcement service.
Checks user's current plan limits and returns whether an action is allowed.
"""
from app.services.billing_service import PLANS


def get_user_plan(user, db=None) -> str:
    """Return effective plan string for user: 'free', 'growth', or 'enterprise'.

    When `db` is provided the function checks the user's Subscription record so
    that a cancelled subscription is honoured until `current_period_end` rather
    than immediately reverting to free.  After the period expires, `user.plan` is
    lazily synced to FREE so future calls without a db session remain accurate.
    """
    if db is not None:
        try:
            from datetime import datetime
            from app.models import Subscription, SubscriptionStatus, PlanType
            sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
            if sub and sub.status == SubscriptionStatus.CANCELLED:
                now = datetime.utcnow()
                if sub.current_period_end and sub.current_period_end > now:
                    # Still within the paid billing period — keep paid access
                    return sub.plan.value if hasattr(sub.plan, 'value') else str(sub.plan)
                else:
                    # Period has ended — lazily sync the denormalized field
                    if user.plan != PlanType.FREE:
                        user.plan = PlanType.FREE
                        db.commit()
                    return "free"
        except Exception:
            pass

    try:
        if user.plan:
            return user.plan.value if hasattr(user.plan, 'value') else str(user.plan)
    except Exception:
        pass
    return "free"


def get_product_headroom(user, db) -> int | None:
    """Return the number of additional products the user may create, or None for unlimited."""
    if getattr(user, 'is_admin', False):
        return None
    plan_key = get_user_plan(user, db)
    limits = PLANS.get(plan_key, PLANS["free"])
    max_products = limits.get("product_limit")
    if max_products is None:
        return None
    from app.models import Product
    current_count = db.query(Product).filter(
        Product.user_id == user.id,
        Product.is_active == True,
    ).count()
    return max(0, max_products - current_count)


def check_product_limit(user, db) -> tuple:
    """
    Returns (allowed: bool, message: str).
    Checks if user can create another product under their plan.
    Admin users always bypass limits.
    """
    # Admin users have unlimited access
    if getattr(user, 'is_admin', False):
        return True, ""

    plan_key = get_user_plan(user, db)
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

    plan_key = get_user_plan(user, db)
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
