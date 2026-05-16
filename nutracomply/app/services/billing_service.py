"""
Razorpay billing service.
All functions fail gracefully — if Razorpay keys are not configured, they return
error dicts rather than raising exceptions.
"""
import hmac
import hashlib
from datetime import datetime
from app.config import get_settings

# Plan definitions — source of truth for prices, limits, and Razorpay order amounts.
# All paise values: 1 INR = 100 paise (e.g. ₹7,999 = 799900 paise).
PLANS = {
    "free": {
        "name": "Starter",
        "price_monthly_paise": 799900,       # ₹7,999/month
        "price_annual_paise": 7999900,        # ₹79,999/year
        "product_limit": 15,
        "scan_limit_monthly": 50,
        "team_seats": 1,
        "features": [
            "15 products (SKUs)",
            "50 scans/month",
            "FSSAI compliance dashboard",
            "Ingredient checker",
            "Daily FSSAI alerts",
            "WhatsApp notifications",
            "FoSCoS renewal tracking",
            "PDF reports",
        ],
    },
    "growth": {
        "name": "Growth",
        "price_monthly_paise": 2199900,       # ₹21,999/month
        "price_annual_paise": 20999900,        # ₹2,09,999/year
        "product_limit": 60,
        "scan_limit_monthly": 250,
        "team_seats": 5,
        "features": [
            "60 products (SKUs)",
            "250 scans/month",
            "Everything in Starter",
            "Automated gap reports",
            "Label audit tool (AI Vision)",
            "Health claim validator",
            "FoSCoS auto-fill",
            "5 team seats",
            "Priority support",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly_paise": 5499900,        # ₹54,999/month — reference only; manual sales
        "price_annual_paise": 49999000,         # ₹4,99,999/year
        "product_limit": None,                  # unlimited
        "scan_limit_monthly": None,
        "team_seats": None,
        "features": [
            "Unlimited products & scans",
            "Everything in Growth",
            "White-label reports",
            "Custom compliance rules",
            "API access",
            "SSO / SAML",
            "Dedicated support",
            "Audit trail",
        ],
    },
}


def create_order(user_id: int, plan: str, billing: str = "monthly") -> dict:
    """
    Create a Razorpay order for the given plan.
    Returns {"order_id": str, "amount": int, "currency": "INR", "key_id": str}
    or {"error": str} on failure.
    """
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        return {"error": "Razorpay not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."}

    plan_data = PLANS.get(plan)
    if not plan_data:
        return {"error": f"Unknown plan: {plan}"}

    amount = (
        plan_data["price_annual_paise"]
        if billing == "annual"
        else plan_data["price_monthly_paise"]
    )
    if amount is None or amount == 0:
        return {"error": "This plan requires manual setup. Please contact sales@regbite.com"}

    try:
        import requests as http_requests
        response = http_requests.post(
            "https://api.razorpay.com/v1/orders",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json={
                "amount": amount,
                "currency": "INR",
                "receipt": f"rb_{user_id}_{plan}_{int(datetime.utcnow().timestamp())}",
                "notes": {"user_id": str(user_id), "plan": plan, "billing": billing},
            },
            timeout=10,
        )
        data = response.json()
        if response.status_code != 200:
            return {"error": data.get("error", {}).get("description", "Razorpay order creation failed")}
        return {
            "order_id": data["id"],
            "amount": amount,
            "currency": "INR",
            "key_id": settings.razorpay_key_id,
        }
    except Exception as e:
        return {"error": f"Payment service unavailable: {e}"}


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature."""
    try:
        settings = get_settings()
        message = f"{order_id}|{payment_id}"
        h = hmac.new(
            settings.razorpay_key_secret.encode(),
            message.encode(),
            hashlib.sha256,
        )
        expected = h.hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify Razorpay webhook signature."""
    try:
        settings = get_settings()
        h = hmac.new(
            settings.razorpay_webhook_secret.encode(),
            body,
            hashlib.sha256,
        )
        expected = h.hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def get_plan_limits(plan: str) -> dict:
    """Return limits for a given plan name. Raises KeyError for unknown plans."""
    if plan not in PLANS:
        raise KeyError(f"Unknown plan: '{plan}'. Valid plans: {list(PLANS.keys())}")
    return PLANS[plan]
