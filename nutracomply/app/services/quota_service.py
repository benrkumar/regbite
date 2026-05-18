"""
Quota enforcement service.
Checks user's current plan limits and returns whether an action is allowed.
"""
from app.services.billing_service import PLANS


def get_user_plan(user, db=None) -> str:
    """Return effective plan string for user: 'free', 'growth', or 'enterprise'.

    Priority order when a Subscription row exists:
    1. TRIALING + within trial window  → return trial plan (growth)
    2. TRIALING + expired              → downgrade to free lazily, return 'free'
    3. ACTIVE                          → return sub.plan
    4. CANCELLED + within period_end   → return sub.plan (grace access)
    5. CANCELLED + expired             → downgrade to free lazily, return 'free'
    6. PAST_DUE                        → return 'free' (access suspended)
    7. No subscription / any exception → fall back to user.plan or 'free'
    """
    if db is not None:
        try:
            from datetime import datetime
            from app.models import Subscription, SubscriptionStatus, PlanType
            sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
            if sub:
                now = datetime.utcnow()

                if sub.status == SubscriptionStatus.TRIALING:
                    end = sub.trial_ends_at or sub.current_period_end
                    if end and end > now:
                        return sub.plan.value if hasattr(sub.plan, 'value') else str(sub.plan)
                    # Trial expired — downgrade lazily
                    sub.status = SubscriptionStatus.CANCELLED
                    if user.plan != PlanType.FREE:
                        user.plan = PlanType.FREE
                    db.commit()
                    return "free"

                if sub.status == SubscriptionStatus.ACTIVE:
                    return sub.plan.value if hasattr(sub.plan, 'value') else str(sub.plan)

                if sub.status == SubscriptionStatus.CANCELLED:
                    if sub.current_period_end and sub.current_period_end > now:
                        return sub.plan.value if hasattr(sub.plan, 'value') else str(sub.plan)
                    if user.plan != PlanType.FREE:
                        user.plan = PlanType.FREE
                        db.commit()
                    return "free"

                if sub.status == SubscriptionStatus.PAST_DUE:
                    return "free"  # suspend access while payment is failing

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
    limits = PLANS.get(plan_key) or PLANS["free"]
    max_products = limits.get("product_limit")
    if max_products is None:
        return None
    from app.models import Product
    current_count = db.query(Product).filter(
        Product.user_id == user.id,
        Product.is_active == True,
        Product.is_quick_check == False,  # ephemeral checker products don't count
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
    limits = PLANS.get(plan_key) or PLANS["free"]
    max_products = limits.get("product_limit")

    if max_products is None:  # unlimited (enterprise)
        return True, ""

    from app.models import Product
    current_count = db.query(Product).filter(
        Product.user_id == user.id,
        Product.is_active == True,
        Product.is_quick_check == False,  # ephemeral checker products don't count
    ).count()

    if current_count >= max_products:
        return False, (
            f"Your {limits['name']} plan allows up to {max_products} products. "
            f"You currently have {current_count}. "
            f"Upgrade to Growth for up to {PLANS['growth']['product_limit']} products."
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
    limits = PLANS.get(plan_key) or PLANS["free"]
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
            f"Upgrade to Growth for {PLANS['growth']['scan_limit_monthly']} scans/month."
        )
    return True, ""
