from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ComplianceRule, RegulationChange, RegulationSource, RuleCategory
from app.routes.auth import get_current_user_from_cookie
from app.services.alert_service import count_unread_alerts
from app.services.regulation_ingestion import derive_source_freshness

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SOURCE_FILTER_GROUPS = {
    "fssai": ["fssai-regulations", "fssai-gazette"],
    "ayush": ["ayush-advisories", "ayush-regulations"],
    "legal_metrology": ["legal-metrology-rules", "legal-metrology-act"],
}


def _normalize_filter(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().replace(" ", "_")
    return None if normalized == "all" else normalized


def _source_family_for_change(change: RegulationChange) -> str:
    if change.source and change.source.slug:
        slug = change.source.slug
        if slug.startswith("ayush"):
            return "ayush"
        if slug.startswith("legal-metrology"):
            return "legal_metrology"
        return "fssai"

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
    freshness: Optional[str] = None,
    review: Optional[str] = None,
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    source_filter = _normalize_filter(source)
    freshness_filter = _normalize_filter(freshness)
    review_filter = _normalize_filter(review)

    changes_query = (
        db.query(RegulationChange)
        .options(joinedload(RegulationChange.source))
        .outerjoin(RegulationSource, RegulationChange.source_id == RegulationSource.id)
        .filter(
            (RegulationChange.crawl_status.is_(None))
            | (RegulationChange.crawl_status == "accepted")
        )
        .order_by(RegulationChange.detected_at.desc())
    )

    if source_filter:
        source_slugs = SOURCE_FILTER_GROUPS.get(source_filter, [source_filter])
        url_patterns = [
            source_filter.replace("_", ""),
            source_filter.replace("_", "-"),
            source_filter.replace("_", " "),
        ]
        changes_query = changes_query.filter(
            or_(
                RegulationSource.slug.in_(source_slugs),
                *[RegulationChange.source_url.ilike(f"%{pattern}%") for pattern in url_patterns],
            )
        )

    if freshness_filter:
        changes_query = changes_query.filter(RegulationSource.freshness_state == freshness_filter)

    if review_filter == "legacy":
        changes_query = changes_query.filter(
            or_(
                RegulationChange.review_state.is_(None),
                RegulationChange.review_state == "legacy",
            )
        )
    elif review_filter:
        changes_query = changes_query.filter(RegulationChange.review_state == review_filter)

    changes = changes_query.all()
    for change in changes:
        if change.source:
            change.source.freshness_state = derive_source_freshness(change.source)

    grouped: OrderedDict[str, list[RegulationChange]] = OrderedDict()
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
    for source_row in source_registry:
        source_row.freshness_state = derive_source_freshness(source_row)

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
        "filter_freshness": freshness_filter or "",
        "filter_review": review_filter or "",
        "unread_alerts": count_unread_alerts(db, user),
        "source_registry": source_registry,
        "source_filter_groups": SOURCE_FILTER_GROUPS,
        "source_family_for_change": _source_family_for_change,
        "freshness_options": ["fresh", "stale", "degraded", "never"],
        "review_options": ["auto_published", "reviewed", "legacy"],
    })
