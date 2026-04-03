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

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


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
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    from app.services.billing_service import PLANS
    settings_obj = None
    try:
        from app.config import get_settings
        settings_obj = get_settings()
    except Exception:
        pass

    razorpay_configured = bool(settings_obj and settings_obj.razorpay_key_id)

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

    if plan not in ("growth",):  # only growth plan is purchasable
        return JSONResponse({"error": "Invalid plan"}, status_code=400)

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

    # Create or update subscription
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    now = datetime.utcnow()
    if not sub:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    sub.plan = PlanType(plan)
    sub.status = SubscriptionStatus.ACTIVE
    sub.razorpay_order_id = order_id
    sub.razorpay_payment_id = payment_id
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=30)

    # Update denormalized plan on user
    user.plan = PlanType(plan)

    db.commit()

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "subscription_upgraded", "subscription", sub.id, detail=f"Upgraded to {plan}")
    except Exception:
        pass

    try:
        from app.services.notify_service import push
        push(user.id, "Subscription activated!",
             "You're now on the Growth plan. Enjoy unlimited access.",
             ntype="success", link="/billing")
    except Exception:
        pass

    # Send payment confirmation email
    try:
        from app.services.notification import send_payment_confirmation_email
        amount_paise = record.amount_paise if record else 299900
        send_payment_confirmation_email(
            user,
            plan=plan,
            amount_display=f"₹{amount_paise // 100:,}",
            period_end=sub.current_period_end.strftime("%d %b %Y"),
        )
    except Exception:
        pass

    return RedirectResponse(
        url="/billing?msg=Payment+successful!+Welcome+to+Growth+plan&type=success",
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
        user.plan = PlanType.FREE
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
                if record and record.status != "paid":
                    record.razorpay_payment_id = payment_id
                    record.status = "paid"
                    db.commit()

        return JSONResponse({"status": "ok"})
    except Exception as e:
        print(f"[webhook] Error: {e}")
        return JSONResponse({"status": "error"}, status_code=500)
