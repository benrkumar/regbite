"""
Billing routes — subscription management, Razorpay payment flow, webhook handler.
"""
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import Alert, AlertStatus, Subscription, PaymentRecord, PlanType, SubscriptionStatus
from app.utils.alerts import get_unread_alert_count
from app.config import get_settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _provision_subscription(user, plan: str, order_id: str, payment_id: str, db: Session) -> Subscription:
    """Idempotently create/update a user's subscription and sync user.plan.

    Safe to call from both the browser-callback verify endpoint AND the
    Razorpay webhook so that payment capture always results in active access
    regardless of which path fires first.
    """
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    now = datetime.utcnow()
    if not sub:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    # Only update if not already ACTIVE for this exact order (idempotency guard)
    if sub.status != SubscriptionStatus.ACTIVE or sub.razorpay_order_id != order_id:
        sub.plan = PlanType(plan)
        sub.status = SubscriptionStatus.ACTIVE
        sub.razorpay_order_id = order_id
        sub.razorpay_payment_id = payment_id
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
        sub.cancelled_at = None
        user.plan = PlanType(plan)
        db.commit()

        try:
            from app.services.activity_service import log_action
            log_action(user.id, "subscription_upgraded", "subscription", sub.id,
                       detail=f"Upgraded to {plan}")
        except Exception:
            pass

        try:
            from app.services.notify_service import push
            from app.services.billing_service import PLANS as _PLANS
            plan_display = _PLANS.get(plan, {}).get("name", plan.title())
            push(user.id, "Subscription activated!",
                 f"You're now on the {plan_display} plan. Enjoy full access.",
                 ntype="success", link="/billing")
        except Exception:
            pass

    return sub


@router.get("/billing")
async def billing_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    payment_history = (
        db.query(PaymentRecord)
        .filter(PaymentRecord.user_id == user.id, PaymentRecord.status == "paid")
        .order_by(PaymentRecord.created_at.desc())
        .limit(10)
        .all()
    )
    unread_alerts = get_unread_alert_count(user, db)

    from app.services.billing_service import PLANS
    settings_obj = None
    try:
        from app.config import get_settings
        settings_obj = get_settings()
    except Exception:
        pass

    razorpay_configured = bool(settings_obj and settings_obj.razorpay_key_id)

    # Trial context — days remaining for TRIALING users
    trial_days_left = None
    trial_ends_display = None
    if (subscription
            and subscription.status == SubscriptionStatus.TRIALING
            and subscription.trial_ends_at):
        delta = subscription.trial_ends_at - datetime.utcnow()
        trial_days_left = max(0, delta.days)
        trial_ends_display = subscription.trial_ends_at.strftime("%d %b %Y")

    return templates.TemplateResponse("billing.html", {
        "request": request,
        "user": user,
        "subscription": subscription,
        "payment_history": payment_history,
        "unread_alerts": unread_alerts,
        "plans": PLANS,
        "razorpay_configured": razorpay_configured,
        "razorpay_key_id": settings_obj.razorpay_key_id if razorpay_configured else "",
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
        "trial_days_left": trial_days_left,
        "trial_ends_display": trial_ends_display,
    })


@router.post("/billing/create-order")
async def create_order(request: Request, db: Session = Depends(get_db)):
    """Create a Razorpay order and return JSON for the frontend."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    form = await request.form()
    plan = (form.get("plan") or "").strip()
    billing = (form.get("billing") or "monthly").strip()

    if plan not in ("free", "growth"):  # enterprise requires manual contracting
        return JSONResponse({"error": "Invalid plan. Contact sales@regbite.com for Enterprise."}, status_code=400)

    if billing not in ("monthly", "annual"):
        return JSONResponse({"error": "Invalid billing period. Must be 'monthly' or 'annual'."}, status_code=400)

    from app.services.billing_service import create_order as _create_order
    result = _create_order(user.id, plan, billing)

    if "error" in result:
        return JSONResponse(result, status_code=400)

    # Record the pending order
    record = PaymentRecord(
        user_id=user.id,
        razorpay_order_id=result["order_id"],
        amount_paise=result["amount"],
        currency="INR",
        plan=PlanType(plan),
        status="created",
    )
    db.add(record)
    db.commit()

    return JSONResponse(result)


@router.post("/billing/verify-payment")
async def verify_payment(request: Request, db: Session = Depends(get_db)):
    """Verify Razorpay payment and activate subscription."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    form = await request.form()
    order_id = (form.get("razorpay_order_id") or "").strip()
    payment_id = (form.get("razorpay_payment_id") or "").strip()
    signature = (form.get("razorpay_signature") or "").strip()
    plan = (form.get("plan") or "growth").strip()

    from app.services.billing_service import verify_payment_signature
    if not verify_payment_signature(order_id, payment_id, signature):
        return RedirectResponse(
            url="/billing?msg=Payment+verification+failed&type=error",
            status_code=302,
        )

    # Update payment record
    record = db.query(PaymentRecord).filter(
        PaymentRecord.razorpay_order_id == order_id,
        PaymentRecord.user_id == user.id,
    ).first()
    if record:
        record.razorpay_payment_id = payment_id
        record.status = "paid"
        db.commit()

    # Provision / activate subscription (idempotent)
    sub = _provision_subscription(user, plan, order_id, payment_id, db)

    # Send payment confirmation email
    try:
        from app.services.notification import send_payment_confirmation_email
        from app.services.billing_service import PLANS as _PLANS
        fallback_paise = _PLANS.get(plan, {}).get("price_monthly_paise", 0)
        amount_paise = record.amount_paise if record else fallback_paise
        send_payment_confirmation_email(
            user,
            plan=plan,
            amount_display=f"₹{amount_paise // 100:,}",
            period_end=sub.current_period_end.strftime("%d %b %Y"),
        )
    except Exception:
        pass

    from app.services.billing_service import PLANS as _PLANS
    plan_display = _PLANS.get(plan, {}).get("name", plan.title())
    return RedirectResponse(
        url=f"/billing?msg=Payment+successful!+Welcome+to+{plan_display.replace(' ', '+')}+plan&type=success",
        status_code=302,
    )


@router.post("/billing/cancel")
async def cancel_subscription(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if sub and sub.status == SubscriptionStatus.ACTIVE:
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = datetime.utcnow()
        access_until = sub.current_period_end.strftime("%d %b %Y") if sub.current_period_end else "end of billing period"
        # Do NOT touch user.plan here — the user retains paid access until
        # current_period_end. quota_service.get_user_plan() checks the
        # subscription period and enforces the downgrade lazily at that point.
        db.commit()

        try:
            from app.services.notification import send_subscription_cancelled_email
            send_subscription_cancelled_email(user, access_until)
        except Exception:
            pass

    return RedirectResponse(
        url="/billing?msg=Subscription+cancelled.+Access+continues+until+end+of+billing+period.&type=info",
        status_code=302,
    )


@router.post("/billing/create-subscription")
async def create_subscription_endpoint(request: Request, db: Session = Depends(get_db)):
    """Create a Razorpay Subscription (recurring) and return JSON for the frontend.

    Falls back to a one-time order when Razorpay plan IDs are not yet configured
    so the upgrade button still works during onboarding / before dashboard setup.
    """
    user = get_current_user_from_cookie(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    form = await request.form()
    plan = (form.get("plan") or "").strip().lower()
    billing = (form.get("billing") or "monthly").strip().lower()

    if plan not in ("free", "growth"):
        return JSONResponse({"error": "Invalid plan."}, status_code=400)
    if billing not in ("monthly", "annual"):
        return JSONResponse({"error": "Invalid billing period."}, status_code=400)

    # Block double-subscription if already active on the same plan
    existing_sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if (existing_sub
            and existing_sub.status == SubscriptionStatus.ACTIVE
            and existing_sub.plan
            and existing_sub.plan.value == plan):
        return JSONResponse({"error": "Already subscribed to this plan."}, status_code=400)

    from app.services.billing_service import create_razorpay_subscription, get_razorpay_plan_id
    plan_id = get_razorpay_plan_id(plan, billing)

    if not plan_id:
        # Razorpay recurring plans not configured — fall back to one-time order
        from app.services.billing_service import create_order as _create_order
        result = _create_order(user.id, plan, billing)
        if "error" in result:
            return JSONResponse(result, status_code=400)
        record = PaymentRecord(
            user_id=user.id,
            razorpay_order_id=result["order_id"],
            amount_paise=result["amount"],
            currency="INR",
            plan=PlanType(plan),
            status="created",
        )
        db.add(record)
        db.commit()
        return JSONResponse({**result, "mode": "order"})

    result = create_razorpay_subscription(user.id, plan, billing)
    if "error" in result:
        return JSONResponse(result, status_code=400)

    settings_obj = get_settings()
    return JSONResponse({**result, "mode": "subscription", "key_id": settings_obj.razorpay_key_id})


@router.post("/billing/verify-subscription")
async def verify_subscription(request: Request, db: Session = Depends(get_db)):
    """Verify the first payment of a Razorpay Subscription and activate the user's plan."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    form = await request.form()
    razorpay_payment_id      = (form.get("razorpay_payment_id") or "").strip()
    razorpay_subscription_id = (form.get("razorpay_subscription_id") or "").strip()
    razorpay_signature       = (form.get("razorpay_signature") or "").strip()
    plan    = (form.get("plan") or "growth").strip().lower()
    billing = (form.get("billing") or "monthly").strip().lower()

    # Subscription payment signature: HMAC-SHA256(payment_id + "|" + subscription_id)
    import hmac as _hmac
    import hashlib as _hashlib
    settings_obj = get_settings()
    msg = f"{razorpay_payment_id}|{razorpay_subscription_id}"
    expected = _hmac.new(
        settings_obj.razorpay_key_secret.encode(),
        msg.encode(),
        _hashlib.sha256,
    ).hexdigest()
    if not _hmac.compare_digest(expected, razorpay_signature):
        return RedirectResponse(
            "/billing?msg=Payment+verification+failed&type=error", status_code=302
        )

    # Provision subscription record
    now = datetime.utcnow()
    period_end = now + (timedelta(days=365) if billing == "annual" else timedelta(days=30))
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if not sub:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    sub.plan = PlanType(plan)
    sub.status = SubscriptionStatus.ACTIVE
    sub.razorpay_sub_id = razorpay_subscription_id
    sub.razorpay_payment_id = razorpay_payment_id
    sub.current_period_start = now
    sub.current_period_end = period_end
    sub.trial_ends_at = None   # clear any remaining trial marker
    sub.cancelled_at = None
    user.plan = PlanType(plan)
    db.commit()

    # Payment record
    from app.services.billing_service import PLANS as _PLANS
    amount = _PLANS.get(plan, {}).get(
        "price_annual_paise" if billing == "annual" else "price_monthly_paise", 0
    )
    record = PaymentRecord(
        user_id=user.id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_subscription_id,  # reuse field to store sub ID
        amount_paise=amount,
        currency="INR",
        plan=PlanType(plan),
        status="paid",
    )
    db.add(record)
    db.commit()

    # Log activity
    try:
        from app.services.activity_service import log_action
        log_action(user.id, "subscription_activated", "subscription", sub.id,
                   detail=f"Activated {plan} via Razorpay subscription")
    except Exception:
        pass

    # Confirmation email
    try:
        from app.services.notification import send_payment_confirmation_email
        send_payment_confirmation_email(
            user,
            plan=plan,
            amount_display=f"₹{amount // 100:,}",
            period_end=period_end.strftime("%d %b %Y"),
        )
    except Exception:
        pass

    # In-app notification
    try:
        from app.services.notify_service import push
        plan_display = _PLANS.get(plan, {}).get("name", plan.title())
        push(user.id, "Subscription activated!",
             f"You're now on the {plan_display} plan. Enjoy full access.",
             ntype="success", link="/billing")
    except Exception:
        pass

    plan_display = _PLANS.get(plan, {}).get("name", plan.title())
    return RedirectResponse(
        f"/billing?msg=Welcome+to+{plan_display.replace(' ', '+')}+plan!&type=success",
        status_code=302,
    )


@router.post("/billing/switch-plan")
async def switch_plan(request: Request, db: Session = Depends(get_db)):
    """Switch between plans.

    Upgrades: cancel existing Razorpay subscription immediately, create a new one
              for the higher plan, return JSON for the frontend to open checkout.
    Downgrades: mark subscription as CANCELLED so quota_service grants access until
                current_period_end, then the user re-subscribes to the lower plan.
    """
    user = get_current_user_from_cookie(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    form = await request.form()
    new_plan = (form.get("plan") or "").strip().lower()
    billing  = (form.get("billing") or "monthly").strip().lower()

    if new_plan not in ("free", "growth"):
        return JSONResponse({"error": "Invalid plan."}, status_code=400)
    if billing not in ("monthly", "annual"):
        return JSONResponse({"error": "Invalid billing period."}, status_code=400)

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if not sub or sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        return JSONResponse({"error": "No active subscription to switch."}, status_code=400)

    current_plan = sub.plan.value if hasattr(sub.plan, "value") else str(sub.plan)
    plan_order = {"free": 0, "growth": 1, "enterprise": 2}
    is_upgrade = plan_order.get(new_plan, 0) > plan_order.get(current_plan, 0)

    if is_upgrade:
        # Cancel existing Razorpay subscription immediately
        if sub.razorpay_sub_id:
            try:
                import requests as _req
                settings_obj = get_settings()
                _req.post(
                    f"https://api.razorpay.com/v1/subscriptions/{sub.razorpay_sub_id}/cancel",
                    auth=(settings_obj.razorpay_key_id, settings_obj.razorpay_key_secret),
                    json={"cancel_at_cycle_end": 0},
                    timeout=10,
                )
            except Exception:
                pass  # proceed anyway — new sub will be independent

        from app.services.billing_service import create_razorpay_subscription
        result = create_razorpay_subscription(user.id, new_plan, billing)
        if "error" in result:
            return JSONResponse(result, status_code=400)
        settings_obj = get_settings()
        return JSONResponse({**result, "mode": "subscription", "key_id": settings_obj.razorpay_key_id})

    else:
        # Downgrade: schedule for end of current period
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = datetime.utcnow()
        db.commit()
        plan_display = {"free": "Starter", "growth": "Growth"}.get(new_plan, new_plan.title())
        return RedirectResponse(
            f"/billing?msg=Downgrade+scheduled.+{plan_display}+plan+starts+after+your+current+period.&type=info",
            status_code=302,
        )


@router.post("/billing/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Razorpay webhooks (payment.captured, subscription.cancelled, etc.)"""
    try:
        body = await request.body()
        signature = request.headers.get("X-Razorpay-Signature", "")

        from app.services.billing_service import verify_webhook_signature
        if not verify_webhook_signature(body, signature):
            return JSONResponse({"status": "invalid signature"}, status_code=400)

        event = json.loads(body)
        event_type = event.get("event")

        if event_type == "payment.captured":
            payment_data = event.get("payload", {}).get("payment", {}).get("entity", {})
            payment_id = payment_data.get("id")
            order_id = payment_data.get("order_id")
            if order_id:
                record = db.query(PaymentRecord).filter(
                    PaymentRecord.razorpay_order_id == order_id
                ).first()
                if record:
                    # Mark payment as paid
                    if record.status != "paid":
                        record.razorpay_payment_id = payment_id
                        record.status = "paid"
                        db.commit()

                    # Provision subscription — handles the case where the
                    # browser callback never fired after payment capture
                    from app.models import User as _User
                    payer = db.query(_User).filter(_User.id == record.user_id).first()
                    if payer:
                        plan_str = record.plan.value if hasattr(record.plan, 'value') else str(record.plan)
                        _provision_subscription(payer, plan_str, order_id, payment_id or "", db)

        elif event_type == "subscription.charged":
            # Recurring payment succeeded — extend the subscription period
            sub_data = event.get("payload", {}).get("subscription", {}).get("entity", {})
            sub_id = sub_data.get("id")
            if sub_id:
                db_sub = db.query(Subscription).filter(
                    Subscription.razorpay_sub_id == sub_id
                ).first()
                if db_sub:
                    now = datetime.utcnow()
                    billing = (sub_data.get("notes") or {}).get("billing", "monthly")
                    delta = timedelta(days=365 if billing == "annual" else 30)
                    db_sub.current_period_start = now
                    db_sub.current_period_end = now + delta
                    db_sub.status = SubscriptionStatus.ACTIVE
                    db.commit()
                    try:
                        from app.models import User as _User
                        from app.services.billing_service import PLANS as _PLANS
                        payer = db.query(_User).filter(_User.id == db_sub.user_id).first()
                        if payer:
                            plan_val = db_sub.plan.value if hasattr(db_sub.plan, "value") else str(db_sub.plan)
                            plan_paise = _PLANS.get(plan_val, {}).get(
                                "price_annual_paise" if billing == "annual"
                                else "price_monthly_paise", 0
                            )
                            from app.services.notification import send_renewal_email
                            send_renewal_email(
                                payer, plan_val,
                                f"₹{plan_paise // 100:,}",
                                db_sub.current_period_end.strftime("%d %b %Y"),
                            )
                    except Exception:
                        pass

        elif event_type == "subscription.halted":
            # Recurring payment failed — suspend access
            sub_data = event.get("payload", {}).get("subscription", {}).get("entity", {})
            sub_id = sub_data.get("id")
            if sub_id:
                db_sub = db.query(Subscription).filter(
                    Subscription.razorpay_sub_id == sub_id
                ).first()
                if db_sub:
                    db_sub.status = SubscriptionStatus.PAST_DUE
                    db.commit()
                    try:
                        from app.models import User as _User
                        payer = db.query(_User).filter(_User.id == db_sub.user_id).first()
                        if payer:
                            plan_val = db_sub.plan.value if hasattr(db_sub.plan, "value") else str(db_sub.plan)
                            from app.services.notification import send_payment_failed_email
                            send_payment_failed_email(payer, plan_val)
                    except Exception:
                        pass

        return JSONResponse({"status": "ok"})
    except Exception as e:
        print(f"[webhook] Error: {e}")
        return JSONResponse({"status": "error"}, status_code=500)
