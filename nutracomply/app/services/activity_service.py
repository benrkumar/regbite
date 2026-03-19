"""
Activity logging service — thin wrapper to record user actions.
All calls are fire-and-forget; errors are caught and printed, never raised.
"""
from datetime import datetime
from app.database import SessionLocal
from app.models import ActivityLog


def log_action(
    user_id,
    action: str,
    resource_type=None,
    resource_id=None,
    detail=None,
    ip_address=None,
):
    """
    Record an activity log entry. Safe to call anywhere — exceptions are swallowed.

    Example actions: "login", "logout", "label_uploaded", "compliance_checked",
    "report_generated", "report_shared", "product_created", "product_deleted",
    "rule_updated", "user_invited", "password_changed", "api_key_created"
    """
    try:
        db = SessionLocal()
        try:
            entry = ActivityLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail,
                ip_address=ip_address,
                created_at=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[activity] Failed to log action '{action}': {e}")
