"""
In-app notification service. Fire-and-forget; errors are swallowed.
"""
from datetime import datetime


def push(user_id: int, title: str, message: str = None,
         ntype: str = "info", link: str = None):
    """Create a Notification record for the user. Safe to call anywhere."""
    try:
        from app.database import SessionLocal
        from app.models import Notification, NotificationType
        db = SessionLocal()
        try:
            n = Notification(
                user_id=user_id,
                title=title,
                message=message,
                ntype=NotificationType(ntype),
                link=link,
                created_at=datetime.utcnow(),
            )
            db.add(n)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[notify] push error: {e}")


def mark_read(user_id: int, notification_id: int):
    try:
        from app.database import SessionLocal
        from app.models import Notification
        db = SessionLocal()
        try:
            n = db.query(Notification).filter(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            ).first()
            if n:
                n.is_read = True
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


def mark_all_read(user_id: int):
    try:
        from app.database import SessionLocal
        from app.models import Notification
        db = SessionLocal()
        try:
            db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False,
            ).update({"is_read": True})
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
