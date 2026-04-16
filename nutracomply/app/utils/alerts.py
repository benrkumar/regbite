"""
Shared alert-count helper.

Always scope unread alert counts to the current user's products so that
different user accounts don't see each other's badge numbers.
"""


def get_unread_alert_count(user, db) -> int:
    """Return the count of unread alerts that belong to the given user.

    Alerts are scoped via Alert.product_id → Product.user_id.
    Alerts without a product_id (e.g. system-wide regulation alerts) are
    not included in per-user badge counts.
    """
    from app.models import Alert, AlertStatus, Product
    return (
        db.query(Alert)
        .join(Product, Alert.product_id == Product.id)
        .filter(
            Alert.status == AlertStatus.UNREAD,
            Product.user_id == user.id,
        )
        .count()
    )
