from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import Notification

router = APIRouter()


@router.get("/notifications")
async def notifications_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    # Mark all as read when viewing the page
    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read == False,
    ).update({"is_read": True})
    db.commit()

    from app.models import Alert, AlertStatus
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "user": user,
        "notifications": notifications,
        "unread_alerts": unread_alerts,
    })


@router.post("/notifications/mark-read")
async def mark_read(request: Request, db: Session = Depends(get_db)):
    """AJAX: mark a single notification read. Body: {id: int}"""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
        nid = int(body.get("id", 0))
        db.query(Notification).filter(
            Notification.id == nid,
            Notification.user_id == user.id,
        ).update({"is_read": True})
        db.commit()
    except Exception:
        pass
    return JSONResponse({"status": "ok"})
