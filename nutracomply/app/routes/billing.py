"""
Billing routes for workspace subscriptions and Razorpay payment flows.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import PaymentRecord, PlanType, Subscription, SubscriptionStatus, User
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import can_manage_billing, get_account_id
from app.services.alert_service import count_unread_alerts

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
settings = get_settings()


def _require_billing_user(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user or not can_manage_billing(user):
        return None
    return user


def _subscription_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(Subscription)
    if account_id:
        query = query.filter(Subscription.account_id == account_id)
    else:
        query = query.filter(Subscription.user_id == user.id)
    return query


def _payment_history_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(PaymentRecord).filter(PaymentRecord.status == "paid")
    if account_id:
        query = query.filter(PaymentRecord.account_id == account_id)
    else:
        query = query.filter(PaymentRecord.user_id == user.id)
    return query


def _sync_workspace_plan_cache(db: Session, user: User, plan: PlanType) -> None:
    account_id = get_account_id(user)
    if account_id:
        db.query(User).filter(User.account_id == account_id).update({"plan": plan})
    else:
        user.plan = plan


def _provision_paid_subscription(
    db: Session,
    record: PaymentRecord,
    *,
    payment_id: str | None = None,
    order_id: str | None = None,
) -> Subscription:
    now = datetime.utcnow()
    subscription = (
        db.query(Subscription)
        .filter(
            Subscription.account_id == record.account_id
            if record.account_id is not None
            else Subscription.user_id == record.user_id
        )
        .first()
    )
    if not subscription:
        subscription = Subscription(user_id=record.user_id, account_id=record.account_id)
        db.add(subscription)

    if payment_id and subscription.razorpay_payment_id == payment_id and subscription.status == SubscriptionStatus.ACTIVE:
        return subscription

    subscription.plan = record.plan
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.razorpay_order_id = order_id or record.razorpay_order_id
    subscription.razorpay_payment_id = payment_id or record.razorpay_payment_id
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=30)
    subscription.cancelled_at = None

    workspace_user = db.query(User).filter(User.id == record.user_id).first()
    if workspace_user:
        _sync_workspace_plan_cache(db, workspace_user, record.plan)
    return subscription


@router.get("/billing")
async def billing_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_manage_billing(user):
        return templates.TemplateResponse("permission_denied.html", {
            "request": request,
            "user": user,
            "unread_alerts": count_unread_alerts(db, user),
            "denied_title": "Billing is limited to account admins",
            "denied_message": "Your role can review workspace results, but only account admins can manage subscriptions, payment history, and billing actions.",
            "back_url": "/dashboard",
            "back_label": "Back to Dashboard",
        }, status_code=403)

    subscription = _subscription_query(db, user).order_by(Subscription.updated_at.desc(), Subscription.id.desc()).first()
    payment_history = _payment_history_query(db, user).order_by(PaymentRecord.created_at.desc()).limit(10).all()

    from app.services.billing_service import PLANS

    return templates.TemplateResponse("billing.html", {
        "request": request,
        "user": user,
        "subscription": subscription,
        "payment_history": payment_history,
        "unread_alerts": count_unread_alerts(db, user),
        "plans": PLANS,
        "razorpay_configured": bool(settings.razorpay_key_id),
        "razorpay_key_id": settings.razorpay_key_id if settings.razorpay_key_id else "",
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
        "can_manage_billing": can_manage_billing(user),
    })


@router.post("/billing/create-order")
async def create_order(request: Request, db: Session = Depends(get_db)):
    user = _require_billing_user(request, db)
    if not user:
        return JSONResponse({"error": "Only account admins can manage billing."}, status_code=403)

    form = await request.form()
    plan = (form.get("plan") or "").strip()
    billing = (form.get("billing") or "monthly").strip()

    if plan not in ("growth",):
        return JSONResponse({"error": "Invalid plan"}, status_code=400)

    from app.services.billing_service import create_order as billing_create_order
    result = billing_create_order(user.id, plan, billing)
    if "error" in result:
        return JSONResponse(result, status_code=400)

    record = PaymentRecord(
        account_id=get_account_id(user),
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
    user = _require_billing_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    form = await request.form()
    order_id = (form.get("razorpay_order_id") or "").strip()
    payment_id = (form.get("razorpay_payment_id") or "").strip()
    signature = (form.get("razorpay_signature") or "").strip()

    from app.services.billing_service import verify_payment_signature

    if not verify_payment_signature(order_id, payment_id, signature):
        return RedirectResponse(url="/billing?msg=Payment+verification+failed&type=error", status_code=302)

    record = (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.razorpay_order_id == order_id,
            PaymentRecord.account_id == get_account_id(user),
        )
        .first()
    )
    if record:
        record.razorpay_payment_id = payment_id
        record.status = "paid"
        subscription = _provision_paid_subscription(db, record, payment_id=payment_id, order_id=order_id)
        db.commit()

        try:
            from app.services.activity_service import log_action
            log_action(user.id, "subscription_upgraded", "subscription", subscription.id, detail=f"Upgraded to {record.plan.value}")
        except Exception:
            pass

        try:
            from app.services.notify_service import push
            push(user.id, "Subscription activated!", "Your workspace is now on the Growth plan.", ntype="success", link="/billing")
        except Exception:
            pass

        try:
            from app.services.notification import send_payment_confirmation_email
            send_payment_confirmation_email(
                user,
                plan=record.plan.value,
                amount_display=f"₹{record.amount_paise // 100:,}",
                period_end=subscription.current_period_end.strftime("%d %b %Y"),
            )
        except Exception:
            pass

    return RedirectResponse(
        url="/billing?msg=Payment+successful!+Your+workspace+plan+is+active&type=success",
        status_code=302,
    )


@router.post("/billing/cancel")
async def cancel_subscription(request: Request, db: Session = Depends(get_db)):
    user = _require_billing_user(request, db)
    if not user:
        return RedirectResponse(url="/dashboard", status_code=302)

    subscription = _subscription_query(db, user).order_by(Subscription.updated_at.desc(), Subscription.id.desc()).first()
    if subscription and subscription.status == SubscriptionStatus.ACTIVE:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        access_until = subscription.current_period_end.strftime("%d %b %Y") if subscription.current_period_end else "end of billing period"
        db.commit()

        try:
            from app.services.notification import send_subscription_cancelled_email
            send_subscription_cancelled_email(user, access_until)
        except Exception:
            pass

    return RedirectResponse(
        url="/billing?msg=Subscription+cancelled.+Access+continues+until+the+current+period+ends.&type=info",
        status_code=302,
    )


@router.post("/billing/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
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
            record = db.query(PaymentRecord).filter(PaymentRecord.razorpay_order_id == order_id).first()
            if record:
                record.razorpay_payment_id = payment_id
                record.status = "paid"
                _provision_paid_subscription(db, record, payment_id=payment_id, order_id=order_id)
                db.commit()
        elif event_type == "payment.failed":
            payment_data = event.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = payment_data.get("order_id")
            record = db.query(PaymentRecord).filter(PaymentRecord.razorpay_order_id == order_id).first()
            if record:
                record.status = "failed"
                db.commit()
        elif event_type == "subscription.cancelled":
            subscription_data = event.get("payload", {}).get("subscription", {}).get("entity", {})
            razorpay_sub_id = subscription_data.get("id")
            subscription = db.query(Subscription).filter(Subscription.razorpay_sub_id == razorpay_sub_id).first()
            if subscription:
                subscription.status = SubscriptionStatus.CANCELLED
                subscription.cancelled_at = datetime.utcnow()
                db.commit()

        return JSONResponse({"status": "ok"})
    except Exception as exc:
        print(f"[webhook] Error: {exc}")
        return JSONResponse({"status": "error"}, status_code=500)
