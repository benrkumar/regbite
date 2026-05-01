"""
Activity logging service.

This module has two jobs:
1. record high-signal user and workspace events safely
2. build normalized presentation data for audit/activity views
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Account,
    APIKey,
    ActivityLog,
    ComplianceReport,
    LabelVersion,
    Notification,
    Product,
    TeamInvite,
    User,
)


ACTION_PRESENTATION = {
    "login": {"label": "Signed in", "tone": "info", "group": "Access"},
    "logout": {"label": "Signed out", "tone": "neutral", "group": "Access"},
    "account_registered": {"label": "Created account", "tone": "success", "group": "Access"},
    "product_created": {"label": "Created product", "tone": "success", "group": "Products"},
    "product_archived": {"label": "Archived product", "tone": "warn", "group": "Products"},
    "product_restored": {"label": "Restored product", "tone": "info", "group": "Products"},
    "product_deleted": {"label": "Removed product", "tone": "bad", "group": "Products"},
    "product_bulk_imported": {"label": "Imported products", "tone": "info", "group": "Products"},
    "label_uploaded": {"label": "Queued label scan", "tone": "info", "group": "Scans"},
    "label_reanalyzed": {"label": "Re-analyzed label", "tone": "info", "group": "Scans"},
    "label_scan_retried": {"label": "Retried failed scan", "tone": "warn", "group": "Scans"},
    "label_scan_completed": {"label": "Completed label scan", "tone": "success", "group": "Scans"},
    "label_scan_failed": {"label": "Label scan failed", "tone": "bad", "group": "Scans"},
    "label_fields_edited": {"label": "Edited extracted fields", "tone": "warn", "group": "Scans"},
    "compliance_checked": {"label": "Ran checker", "tone": "info", "group": "Compliance"},
    "checker_run": {"label": "Ran checker", "tone": "info", "group": "Compliance"},
    "report_generated": {"label": "Generated report", "tone": "success", "group": "Reports"},
    "report_shared": {"label": "Shared report", "tone": "info", "group": "Reports"},
    "report_downloaded": {"label": "Downloaded report", "tone": "neutral", "group": "Reports"},
    "notification_preferences_updated": {"label": "Updated notification emails", "tone": "info", "group": "Settings"},
    "profile_updated": {"label": "Updated profile", "tone": "neutral", "group": "Settings"},
    "password_changed": {"label": "Changed password", "tone": "warn", "group": "Security"},
    "branding_updated": {"label": "Updated report branding", "tone": "info", "group": "Settings"},
    "api_key_created": {"label": "Created API key", "tone": "warn", "group": "Security"},
    "api_key_revoked": {"label": "Revoked API key", "tone": "bad", "group": "Security"},
    "subscription_upgraded": {"label": "Changed subscription", "tone": "success", "group": "Billing"},
    "team_invite_created": {"label": "Invited teammate", "tone": "info", "group": "Team"},
    "team_invite_revoked": {"label": "Revoked invite", "tone": "warn", "group": "Team"},
    "team_role_updated": {"label": "Updated team role", "tone": "info", "group": "Team"},
    "team_member_removed": {"label": "Removed teammate", "tone": "bad", "group": "Team"},
    "team_invite_accepted": {"label": "Joined workspace", "tone": "success", "group": "Team"},
    "admin_role_updated": {"label": "Updated admin role", "tone": "warn", "group": "Admin"},
    "admin_status_updated": {"label": "Updated user status", "tone": "warn", "group": "Admin"},
}


RESOURCE_LINKS = {
    "product": "/products/{id}",
    "label": "/labels/{id}",
    "report": "/reports/{id}",
    "api_key": "/settings/api-keys",
    "team_invite": "/team",
    "subscription": "/billing",
    "checker_session": "/checker",
}


def _request_ip(request) -> str | None:
    if not request:
        return None
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


def _request_user_agent(request) -> str | None:
    if not request:
        return None
    headers = getattr(request, "headers", {}) or {}
    try:
        return (headers.get("user-agent") or "").strip()[:300] or None
    except Exception:
        return None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return {"raw": str(value)}


def log_action(
    user_id,
    action: str,
    resource_type=None,
    resource_id=None,
    detail=None,
    ip_address=None,
    *,
    request=None,
    account_id=None,
    target_user_id=None,
    status: str = "success",
    context: dict[str, Any] | None = None,
    user_agent: str | None = None,
):
    """
    Record an activity log entry. Safe to call anywhere; exceptions are swallowed.
    """
    try:
        db = SessionLocal()
        try:
            derived_account_id = account_id
            if derived_account_id is None and user_id:
                actor = db.query(User).filter(User.id == user_id).first()
                derived_account_id = actor.account_id if actor else None

            entry = ActivityLog(
                account_id=derived_account_id,
                user_id=user_id,
                target_user_id=target_user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=(detail or "")[:500] or None,
                status=(status or "success")[:20],
                ip_address=(ip_address or _request_ip(request) or None),
                user_agent=(user_agent or _request_user_agent(request) or None),
                context_json=_json_safe(context) or {},
                created_at=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        print(f"[activity] Failed to log action '{action}': {exc}")


def present_action(action: str | None) -> dict[str, str]:
    info = ACTION_PRESENTATION.get(action or "", None)
    if info:
        return info
    action_text = (action or "event").replace("_", " ").strip().title()
    return {"label": action_text, "tone": "neutral", "group": "Activity"}


def resource_link(resource_type: str | None, resource_id: int | None) -> str | None:
    if not resource_type:
        return None
    template = RESOURCE_LINKS.get(resource_type)
    if not template:
        return None
    if "{id}" in template:
        if resource_id is None:
            return None
        return template.format(id=resource_id)
    return template


def decorate_logs(logs: list[ActivityLog]) -> list[dict[str, Any]]:
    decorated = []
    for log in logs:
        info = present_action(log.action)
        decorated.append({
            "entry": log,
            "label": info["label"],
            "tone": info["tone"],
            "group": info["group"],
            "resource_link": resource_link(log.resource_type, log.resource_id),
        })
    return decorated


def _pick_actions(
    decorated_logs: list[dict[str, Any]],
    *,
    groups: set[str] | None = None,
    actions: set[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    items = []
    for item in decorated_logs:
        action_name = item["entry"].action
        if groups and item["group"] not in groups:
            continue
        if actions and action_name not in actions:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def query_user_activity(db: Session, target_user: User, *, limit: int = 20) -> list[ActivityLog]:
    return (
        db.query(ActivityLog)
        .filter(
            or_(
                ActivityLog.user_id == target_user.id,
                ActivityLog.target_user_id == target_user.id,
            )
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )


def query_account_activity(db: Session, account_id: int | None, *, limit: int = 20) -> list[ActivityLog]:
    if not account_id:
        return []
    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.account_id == account_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )
    for item in logs:
        _ = item.user
        _ = item.target_user
    return logs


def build_user_audit_snapshot(db: Session, target_user: User, *, limit: int = 20) -> dict[str, Any]:
    account_id = getattr(target_user, "account_id", None)
    account = db.query(Account).filter(Account.id == account_id).first() if account_id else None

    products_q = db.query(Product).filter(Product.user_id == target_user.id, Product.is_temporary == False)
    labels_q = (
        db.query(LabelVersion)
        .join(Product, Product.id == LabelVersion.product_id)
        .filter(Product.user_id == target_user.id)
    )
    reports_q = db.query(ComplianceReport).filter(ComplianceReport.user_id == target_user.id)
    notifications_q = db.query(Notification).filter(Notification.user_id == target_user.id)
    keys_q = db.query(APIKey).filter(APIKey.user_id == target_user.id, APIKey.is_active == True)

    recent_activity = query_user_activity(db, target_user, limit=limit)
    recent_products = products_q.order_by(Product.updated_at.desc(), Product.created_at.desc()).limit(5).all()
    recent_labels = labels_q.order_by(LabelVersion.uploaded_at.desc()).limit(5).all()
    recent_reports = reports_q.order_by(ComplianceReport.created_at.desc()).limit(5).all()
    recent_notifications = notifications_q.order_by(Notification.created_at.desc()).limit(5).all()
    recent_api_keys = keys_q.order_by(APIKey.created_at.desc()).limit(5).all()
    recent_team_invites = []
    if account_id:
        recent_team_invites = (
            db.query(TeamInvite)
            .filter(TeamInvite.account_id == account_id)
            .order_by(TeamInvite.created_at.desc())
            .limit(5)
            .all()
        )

    for item in recent_activity:
        _ = item.user
        _ = item.target_user
    for label in recent_labels:
        _ = label.product
    for report in recent_reports:
        _ = report.product

    last_login = next((item for item in recent_activity if item.action == "login"), None)
    last_logout = next((item for item in recent_activity if item.action == "logout"), None)
    last_upload = next((item for item in recent_activity if item.action == "label_uploaded"), None)
    last_report = next((item for item in recent_activity if item.action in {"report_generated", "report_shared", "report_downloaded"}), None)
    last_security = next((item for item in recent_activity if item.action in {"password_changed", "api_key_created", "api_key_revoked"}), None)
    last_scan = next((item for item in recent_activity if item.action in {"label_uploaded", "label_reanalyzed", "label_scan_retried", "label_scan_completed", "label_scan_failed"}), None)
    latest_label_record = recent_labels[0] if recent_labels else None
    latest_report_record = recent_reports[0] if recent_reports else None

    last_login_at = last_login.created_at if last_login else None
    last_scan_at = (
        last_scan.created_at
        if last_scan
        else (
            latest_label_record.processing_finished_at
            if latest_label_record and latest_label_record.processing_finished_at
            else latest_label_record.uploaded_at if latest_label_record else None
        )
    )
    last_report_at = last_report.created_at if last_report else (latest_report_record.created_at if latest_report_record else None)
    last_security_at = last_security.created_at if last_security else None

    last_30_days = datetime.utcnow() - timedelta(days=30)
    activity_last_30d = [
        item for item in recent_activity
        if item.created_at and item.created_at >= last_30_days
    ]
    group_counts = Counter(present_action(item.action)["group"] for item in activity_last_30d)
    recent_activity_display = decorate_logs(recent_activity)
    access_activity = _pick_actions(
        recent_activity_display,
        groups={"Access", "Security"},
        actions={
            "login",
            "logout",
            "account_registered",
            "password_changed",
            "api_key_created",
            "api_key_revoked",
        },
    )
    scan_activity = _pick_actions(recent_activity_display, groups={"Scans"}, limit=6)
    team_activity = _pick_actions(recent_activity_display, groups={"Team"}, limit=6)
    settings_activity = _pick_actions(recent_activity_display, groups={"Settings"}, limit=6)
    activity_mix = [
        {"group": group, "count": count}
        for group, count in sorted(
            group_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    team_members_count = 1
    pending_invites_count = 0
    if account_id:
        team_members_count = db.query(User).filter(User.account_id == account_id, User.is_active == True).count()
        pending_invites_count = db.query(TeamInvite).filter(
            TeamInvite.account_id == account_id,
            TeamInvite.is_accepted == False,
            TeamInvite.expires_at > datetime.utcnow(),
        ).count()

    return {
        "workspace": {
            "name": (account.name if account and account.name else None) or (target_user.name and f"{target_user.name}'s workspace") or "Workspace",
            "company_name": target_user.company_name or (account.company_name if account else None),
            "company_gstin": target_user.company_gstin or (account.company_gstin if account else None),
            "branding_name": target_user.report_brand_name or (account.report_brand_name if account else None) or "RegBite",
            "branding_color": target_user.report_brand_color or (account.report_brand_color if account else None),
            "notification_emails": target_user.notification_emails or [],
        },
        "recent_activity": recent_activity,
        "recent_activity_display": recent_activity_display,
        "access_activity": access_activity,
        "scan_activity": scan_activity,
        "team_activity": team_activity,
        "settings_activity": settings_activity,
        "activity_mix": activity_mix,
        "recent_products": recent_products,
        "recent_labels": recent_labels,
        "recent_reports": recent_reports,
        "recent_notifications": recent_notifications,
        "recent_api_keys": recent_api_keys,
        "recent_team_invites": recent_team_invites,
        "last_login": last_login,
        "last_logout": last_logout,
        "last_upload": last_upload,
        "last_report": last_report,
        "last_security": last_security,
        "last_scan": last_scan,
        "last_login_at": last_login_at,
        "last_scan_at": last_scan_at,
        "last_report_at": last_report_at,
        "last_security_at": last_security_at,
        "counts": {
            "products": products_q.count(),
            "labels": labels_q.count(),
            "reports": reports_q.count(),
            "shared_reports": reports_q.filter(ComplianceReport.share_token.isnot(None)).count(),
            "notifications_total": notifications_q.count(),
            "notifications_unread": notifications_q.filter(Notification.is_read == False).count(),
            "active_api_keys": keys_q.count(),
            "team_members": team_members_count,
            "pending_invites": pending_invites_count,
            "notification_recipients": len(target_user.notification_emails or []),
            "access_events_30d": group_counts.get("Access", 0),
            "scan_events_30d": group_counts.get("Scans", 0),
            "security_events_30d": group_counts.get("Security", 0),
            "team_events_30d": group_counts.get("Team", 0),
            "activity_total": (
                db.query(ActivityLog)
                .filter(or_(ActivityLog.user_id == target_user.id, ActivityLog.target_user_id == target_user.id))
                .count()
            ),
        },
        "group_counts_30d": dict(group_counts),
    }
