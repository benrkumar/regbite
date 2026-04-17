from collections import OrderedDict
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from app.database import get_db
from app.models import RegulationChange, ComplianceRule, RuleCategory
from app.routes.auth import get_current_user_from_cookie
from app.utils.alerts import get_unread_alert_count

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/regulations")
async def regulations_feed(
    request: Request,
    db: Session = Depends(get_db),
    tab: str = "feed",
    category: Optional[str] = None,
    severity: Optional[str] = None,
    source: Optional[str] = None,
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    changes_q = db.query(RegulationChange).order_by(RegulationChange.detected_at.desc())
    if source:
        changes_q = changes_q.filter(RegulationChange.source_url.ilike(f"%{source}%"))
    changes = changes_q.all()

    # Group changes by Month Year (ordered, newest first)
    grouped: OrderedDict = OrderedDict()
    for change in changes:
        key = change.detected_at.strftime("%B %Y")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(change)
    grouped_changes = [{"label": k, "changes": v} for k, v in grouped.items()]

    # Rules database with optional filters
    rules_q = db.query(ComplianceRule).filter(ComplianceRule.active == True)
    if category:
        rules_q = rules_q.filter(ComplianceRule.category == category)
    if severity:
        rules_q = rules_q.filter(ComplianceRule.severity == severity)
    rules = rules_q.order_by(ComplianceRule.category, ComplianceRule.rule_code).all()

    rule_categories = [c.value for c in RuleCategory]

    unread_alerts = get_unread_alert_count(user, db)

    return templates.TemplateResponse("regulations.html", {
        "request": request,
        "user": user,
        "changes": changes,
        "grouped_changes": grouped_changes,
        "rules": rules,
        "rule_categories": rule_categories,
        "active_tab": tab,
        "filter_category": category or "",
        "filter_severity": severity or "",
        "filter_source": source or "",
        "unread_alerts": unread_alerts,
    })
