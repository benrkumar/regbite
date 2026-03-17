from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from app.database import get_db
from app.models import RegulationChange, ComplianceRule, RuleCategory
from app.routes.auth import get_current_user_from_cookie

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/regulations")
async def regulations_feed(
    request: Request,
    db: Session = Depends(get_db),
    tab: str = "feed",
    category: Optional[str] = None,
    severity: Optional[str] = None,
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    changes = (
        db.query(RegulationChange)
        .order_by(RegulationChange.detected_at.desc())
        .all()
    )

    # Rules database with optional filters
    rules_q = db.query(ComplianceRule).filter(ComplianceRule.active == True)
    if category:
        rules_q = rules_q.filter(ComplianceRule.category == category)
    if severity:
        rules_q = rules_q.filter(ComplianceRule.severity == severity)
    rules = rules_q.order_by(ComplianceRule.category, ComplianceRule.rule_code).all()

    rule_categories = [c.value for c in RuleCategory]

    from app.models import Alert, AlertStatus
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("regulations.html", {
        "request": request,
        "user": user,
        "changes": changes,
        "rules": rules,
        "rule_categories": rule_categories,
        "active_tab": tab,
        "filter_category": category or "",
        "filter_severity": severity or "",
        "unread_alerts": unread_alerts,
    })


@router.post("/regulations/trigger-scrape")
async def trigger_manual_scrape(request: Request, db: Session = Depends(get_db)):
    """Manually trigger a scrape (useful for testing)."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    try:
        from app.workers.scrape_task import run_fssai_scrape
        run_fssai_scrape.delay()
        message = "Scrape job queued. Results will appear shortly."
    except Exception as e:
        message = f"Could not queue scrape: {e}"

    return RedirectResponse(url="/regulations?msg=" + message, status_code=302)


@router.post("/regulations/trigger-recheck")
async def trigger_manual_recheck(request: Request, db: Session = Depends(get_db)):
    """Manually trigger a full label re-check."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    try:
        from app.workers.recheck_task import recheck_all_labels
        recheck_all_labels.delay()
        message = "Re-check job queued."
    except Exception as e:
        message = f"Could not queue re-check: {e}"

    return RedirectResponse(url="/regulations?msg=" + message, status_code=302)
