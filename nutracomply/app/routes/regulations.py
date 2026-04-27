from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ComplianceRule, RegulationChange, RegulationSource, RuleCategory
from app.routes.auth import get_current_user_from_cookie
from app.services.alert_service import count_unread_alerts

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _normalize_source_filter(source: str | None) -> str | None:
    if not source:
        return None
    normalized = source.strip().lower().replace(" ", "_")
    mapping = {
        "all": None,
        "fssai": "fssai",
        "ayush": "ayush",
        "legal_metrology": "legal_metrology",
    }
    return mapping.get(normalized, normalized)


def _source_slug_for_change(change: RegulationChange) -> str:
    if change.source and change.source.slug:
        return change.source.slug

    url = (change.source_url or "").lower()
    if "ayush" in url:
        return "ayush"
    if "consumeraffairs" in url or "legalmetrology" in url:
        return "legal_metrology"
    return "fssai"


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

    source_filter = _normalize_source_filter(source)
    changes_query = (
        db.query(RegulationChange)
        .options(joinedload(RegulationChange.source))
        .order_by(RegulationChange.detected_at.desc())
    )
    if source_filter:
        changes_query = changes_query.outerjoin(RegulationSource, RegulationChange.source_id == RegulationSource.id).filter(
            (RegulationSource.slug == source_filter)
            | RegulationChange.source_url.ilike(f"%{source_filter.replace('_', '')}%")
            | RegulationChange.source_url.ilike(f"%{source_filter.replace('_', '-')}%")
            | RegulationChange.source_url.ilike(f"%{source_filter.replace('_', ' ')}%")
        )
    changes = changes_query.all()

    grouped: OrderedDict = OrderedDict()
    for change in changes:
        key = change.detected_at.strftime("%B %Y")
        grouped.setdefault(key, []).append(change)
    grouped_changes = [{"label": label, "changes": items} for label, items in grouped.items()]

    rules_q = db.query(ComplianceRule).filter(ComplianceRule.active == True)
    if category:
        rules_q = rules_q.filter(ComplianceRule.category == category)
    if severity:
        rules_q = rules_q.filter(ComplianceRule.severity == severity)
    rules = rules_q.order_by(ComplianceRule.category, ComplianceRule.rule_code).all()

    source_registry = (
        db.query(RegulationSource)
        .filter(RegulationSource.is_active == True)
        .order_by(RegulationSource.name.asc())
        .all()
    )

    return templates.TemplateResponse("regulations.html", {
        "request": request,
        "user": user,
        "changes": changes,
        "grouped_changes": grouped_changes,
        "rules": rules,
        "rule_categories": [c.value for c in RuleCategory],
        "active_tab": tab,
        "filter_category": category or "",
        "filter_severity": severity or "",
        "filter_source": source_filter or "",
        "unread_alerts": count_unread_alerts(db, user),
        "source_registry": source_registry,
        "source_slug_for_change": _source_slug_for_change,
    })
