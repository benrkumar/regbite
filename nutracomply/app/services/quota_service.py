"""
Quota enforcement service.
Checks workspace-level limits using the active subscription when available.
"""
from __future__ import annotations

from datetime import datetime

from app.models import Product, LabelVersion, Subscription, SubscriptionStatus
from app.services.access_control import get_account_id, is_platform_admin
from app.services.billing_service import PLANS


ACTIVE_SUBSCRIPTION_STATUSES = {
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.TRIALING,
}


def _normalize_plan(value) -> str:
    if not value:
        return "free"
    return value.value if hasattr(value, "value") else str(value)


def get_active_subscription(user, db) -> Subscription | None:
    account_id = get_account_id(user)
    query = db.query(Subscription)
    if account_id:
        query = query.filter(Subscription.account_id == account_id)
    else:
        query = query.filter(Subscription.user_id == user.id)

    now = datetime.utcnow()
    subscriptions = query.order_by(Subscription.updated_at.desc(), Subscription.id.desc()).all()
    for subscription in subscriptions:
        if subscription.status in ACTIVE_SUBSCRIPTION_STATUSES:
            return subscription
        if (
            subscription.status == SubscriptionStatus.CANCELLED
            and subscription.current_period_end
            and subscription.current_period_end >= now
        ):
            return subscription
    return None


def get_user_plan(user, db=None) -> str:
    """Return effective workspace plan: free, growth, or enterprise."""
    if db is not None and user is not None:
        subscription = get_active_subscription(user, db)
        if subscription and subscription.plan:
            return _normalize_plan(subscription.plan)
    return _normalize_plan(getattr(user, "plan", None))


def _workspace_product_query(user, db):
    account_id = get_account_id(user)
    query = db.query(Product).filter(
        Product.is_active == True,
        Product.is_temporary == False,
        Product.is_sample == False,
    )
    if account_id:
        query = query.filter(Product.account_id == account_id)
    else:
        query = query.filter(Product.user_id == user.id)
    return query


def check_product_limit(user, db) -> tuple:
    """
    Returns (allowed: bool, message: str).
    Checks if the current workspace can create another canonical product.
    """
    if is_platform_admin(user):
        return True, ""

    plan_key = get_user_plan(user, db)
    limits = PLANS.get(plan_key, PLANS["free"])
    max_products = limits.get("product_limit")

    if max_products is None:
        return True, ""

    current_count = _workspace_product_query(user, db).count()
    if current_count >= max_products:
        return False, (
            f"Your {limits['name']} plan allows up to {max_products} products. "
            f"Your workspace currently has {current_count}. "
            "Upgrade to Growth for up to 25 products."
        )
    return True, ""


def check_scan_limit(user, db) -> tuple:
    """
    Returns (allowed: bool, message: str).
    Counts only canonical workspace scans. Ephemeral checker sessions and sample
    data do not consume paid scan quotas until promoted.
    """
    if is_platform_admin(user):
        return True, ""

    plan_key = get_user_plan(user, db)
    limits = PLANS.get(plan_key, PLANS["free"])
    max_scans = limits.get("scan_limit_monthly")

    if max_scans is None:
        return True, ""

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    account_id = get_account_id(user)

    query = (
        db.query(LabelVersion)
        .join(Product, LabelVersion.product_id == Product.id)
        .filter(
            Product.is_active == True,
            Product.is_temporary == False,
            Product.is_sample == False,
            LabelVersion.uploaded_at >= month_start,
        )
    )
    if account_id:
        query = query.filter(Product.account_id == account_id)
    else:
        query = query.filter(Product.user_id == user.id)

    scans_this_month = query.count()
    if scans_this_month >= max_scans:
        return False, (
            f"Your {limits['name']} plan allows {max_scans} scans per month. "
            f"Your workspace has used {scans_this_month} this month. "
            "Upgrade to Growth for 100 scans/month."
        )
    return True, ""
