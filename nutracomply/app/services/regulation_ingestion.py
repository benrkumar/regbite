from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AlertStatus,
    AlertType,
    ChangeType,
    RegulationChange,
    RegulationCrawlRun,
    RegulationSource,
    RegulationStatus,
    Severity,
)
from app.services.scraper import (
    DownloadedDocument,
    SourceDiscovery,
    build_source_document_key,
    classify_regulation_change,
    discover_documents_for_source,
    download_document,
    evaluate_discovery,
    get_default_source_config,
    resolve_source_family_slug,
)

log = logging.getLogger("regbite.regulation_ingestion")

FRESHNESS_SLA_HOURS = 36


def derive_source_freshness(source: RegulationSource | None, now: datetime | None = None) -> str:
    if not source:
        return "unknown"

    now = now or datetime.utcnow()
    last_success = getattr(source, "last_success_at", None)
    last_error = getattr(source, "last_error_at", None)

    if not last_success:
        return "never"
    if last_error and last_error >= last_success:
        return "degraded"
    if last_success >= now - timedelta(hours=FRESHNESS_SLA_HOURS):
        return "fresh"
    return "stale"


def match_source_for_url(sources: Iterable[RegulationSource], url: str | None) -> RegulationSource | None:
    target = (url or "").lower()
    if not target:
        return None

    family = _family_for_url(target)
    candidates = list(sources)

    for source in candidates:
        if source.base_url and source.base_url.lower() in target:
            return source

    scored_match: tuple[int, RegulationSource] | None = None
    for source in candidates:
        slug_tokens = [token for token in source.slug.split("-") if len(token) > 3]
        score = sum(1 for token in slug_tokens if token in target)
        if score and (scored_match is None or score > scored_match[0]):
            scored_match = (score, source)

    if scored_match:
        return scored_match[1]

    if family:
        for source in candidates:
            if resolve_source_family_slug(source.slug) == family:
                return source

    return None


def crawl_active_regulation_sources(
    db: Session,
    *,
    source_ids: list[int] | None = None,
    initiated_by: str = "scheduler",
) -> dict:
    query = (
        db.query(RegulationSource)
        .filter(RegulationSource.is_active == True)
        .order_by(RegulationSource.name.asc())
    )
    if source_ids:
        query = query.filter(RegulationSource.id.in_(source_ids))

    sources = query.all()
    summary = {
        "source_count": len(sources),
        "discovery_count": 0,
        "accepted_count": 0,
        "reject_count": 0,
        "unchanged_count": 0,
        "sources": [],
        "accepted_changes": [],
    }

    for source in sources:
        result = crawl_regulation_source(db, source, initiated_by=initiated_by)
        summary["discovery_count"] += result["discovery_count"]
        summary["accepted_count"] += result["accepted_count"]
        summary["reject_count"] += result["reject_count"]
        summary["unchanged_count"] += result["unchanged_count"]
        summary["sources"].append(result)
        summary["accepted_changes"].extend(result["accepted_changes"])

    return summary


def crawl_regulation_source(
    db: Session,
    source: RegulationSource,
    *,
    initiated_by: str = "scheduler",
) -> dict:
    started_at = datetime.utcnow()
    source.last_checked_at = started_at
    source.last_crawled_at = started_at
    source.last_status = "running"
    source.freshness_state = derive_source_freshness(source, started_at)

    run = RegulationCrawlRun(
        source_id=source.id,
        initiated_by=initiated_by,
        started_at=started_at,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    accepted_changes: list[RegulationChange] = []
    discovery_count = 0
    accepted_count = 0
    reject_count = 0
    unchanged_count = 0
    first_reject_reason: str | None = None

    try:
        discoveries = discover_documents_for_source(source)
        discovery_count = len(discoveries)

        for discovery in discoveries:
            outcome = process_source_discovery(db, source, discovery)
            action = outcome["action"]
            if action == "accepted":
                accepted_count += 1
                accepted_changes.append(outcome["change"])
            elif action == "rejected":
                reject_count += 1
                first_reject_reason = first_reject_reason or outcome.get("reason")
            elif action == "unchanged":
                unchanged_count += 1

        finished_at = datetime.utcnow()
        source.last_success_at = finished_at
        source.last_status = "success"
        source.last_discovery_count = discovery_count
        source.last_reject_count = reject_count
        source.last_reject_reason = first_reject_reason
        source.last_error_message = None
        source.freshness_state = derive_source_freshness(source, finished_at)

        run.finished_at = finished_at
        run.status = "success"
        run.discovery_count = discovery_count
        run.accepted_count = accepted_count
        run.reject_count = reject_count
        run.unchanged_count = unchanged_count
        db.commit()
    except Exception as exc:
        finished_at = datetime.utcnow()
        source.last_status = "failed"
        source.last_error_at = finished_at
        source.last_error_message = str(exc)[:500]
        source.last_discovery_count = discovery_count
        source.last_reject_count = reject_count
        source.last_reject_reason = first_reject_reason
        source.freshness_state = derive_source_freshness(source, finished_at)

        run.finished_at = finished_at
        run.status = "failed"
        run.discovery_count = discovery_count
        run.accepted_count = accepted_count
        run.reject_count = reject_count
        run.unchanged_count = unchanged_count
        run.error_summary = str(exc)[:1000]
        db.commit()
        log.error("[regulations] crawl failed for %s: %s", source.slug, exc)

    return {
        "source": source,
        "run": run,
        "discovery_count": discovery_count,
        "accepted_count": accepted_count,
        "reject_count": reject_count,
        "unchanged_count": unchanged_count,
        "accepted_changes": accepted_changes,
    }


def process_source_discovery(db: Session, source: RegulationSource, discovery: SourceDiscovery) -> dict:
    accepted, reject_reason = evaluate_discovery(source, discovery)
    if not accepted:
        change = _record_rejected_change(db, source, discovery, reject_reason or "Rejected by discovery classifier", "rejected")
        return {"action": "rejected", "change": change, "reason": reject_reason}

    config = _source_config(source)
    downloaded = download_document(
        discovery.source_url,
        max_pdf_pages=_safe_int(config.get("pdf_page_cap")),
        max_text_chars=_safe_int(config.get("max_text_chars"), 20000),
    )
    if not downloaded:
        reason = "Document download failed"
        change = _record_rejected_change(db, source, discovery, reason, "download_failed")
        return {"action": "rejected", "change": change, "reason": reason}

    latest = _latest_change_for_document(db, source.id, discovery.source_document_key)
    if latest and latest.document_hash == downloaded.sha256:
        return {"action": "unchanged", "change": latest}

    classification = classify_regulation_change(discovery.document_name, downloaded.text or "")
    change = _create_published_change(db, source, discovery, downloaded, classification, latest)
    _publish_regulation_change(db, change)
    return {"action": "accepted", "change": change}


def build_change_backfill_payload(change: RegulationChange, sources: list[RegulationSource]) -> dict:
    matched_source = change.source or match_source_for_url(sources, change.source_url)
    family = _family_for_url((change.source_url or "").lower())
    fallback_slug = {
        "fssai": "fssai-regulations",
        "ayush": "ayush-regulations",
        "legal_metrology": "legal-metrology-rules",
    }.get(family, "fssai-regulations")
    source_slug = matched_source.slug if matched_source else fallback_slug
    payload = {
        "source_id": matched_source.id if matched_source else change.source_id,
        "document_type": change.document_type or (matched_source.doc_type if matched_source else None),
        "source_document_key": change.source_document_key or build_source_document_key(
            source_slug or "fssai",
            change.source_url or change.document_name or str(change.id),
            change.document_name,
        ),
        "crawl_status": change.crawl_status or "accepted",
        "review_state": change.review_state or "legacy",
        "published_at": change.published_at or change.detected_at,
    }

    if change.total_page_count is None and change.diff_text:
        payload["total_page_count"] = 1
    if change.extracted_page_count is None and change.diff_text:
        payload["extracted_page_count"] = 1

    return payload


def visible_regulation_change_query(db: Session):
    return db.query(RegulationChange).filter(
        (RegulationChange.crawl_status.is_(None))
        | (RegulationChange.crawl_status == "accepted")
    )


def _create_published_change(
    db: Session,
    source: RegulationSource,
    discovery: SourceDiscovery,
    downloaded: DownloadedDocument,
    classification: dict,
    latest: RegulationChange | None,
) -> RegulationChange:
    now = datetime.utcnow()
    change_type = _parse_change_type(classification.get("change_type"))
    severity = _parse_severity(classification.get("severity"))
    effective_date = _parse_effective_date(classification.get("effective_date"))

    change = RegulationChange(
        source_id=source.id,
        source_url=discovery.source_url,
        source_document_key=discovery.source_document_key,
        document_name=discovery.document_name,
        detected_at=now,
        change_type=change_type,
        summary_text=classification.get("summary_text", ""),
        diff_text=(downloaded.text or "")[:5000],
        effective_date=effective_date,
        severity=severity,
        status="NEW",
        regulation_status=RegulationStatus.EFFECTIVE,
        document_hash=downloaded.sha256,
        document_type=discovery.document_type or source.doc_type,
        crawl_status="accepted",
        published_at=now,
        review_state="auto_published",
        extracted_page_count=downloaded.extracted_pages,
        total_page_count=downloaded.total_pages,
    )
    db.add(change)
    db.commit()
    db.refresh(change)

    if latest and latest.id != change.id:
        latest.superseded_by_change_id = change.id
        latest.status = "SUPERSEDED"
        latest.regulation_status = RegulationStatus.SUPERSEDED
        change.supersedes_change_id = latest.id
        db.commit()
        db.refresh(change)

    return change


def _record_rejected_change(
    db: Session,
    source: RegulationSource,
    discovery: SourceDiscovery,
    reason: str,
    crawl_status: str,
) -> RegulationChange:
    existing = (
        db.query(RegulationChange)
        .filter(
            RegulationChange.source_id == source.id,
            RegulationChange.source_document_key == discovery.source_document_key,
            RegulationChange.crawl_status == crawl_status,
        )
        .order_by(RegulationChange.detected_at.desc())
        .first()
    )

    if existing and existing.reject_reason == reason and existing.source_url == discovery.source_url:
        existing.detected_at = datetime.utcnow()
        existing.document_name = discovery.document_name
        db.commit()
        return existing

    change = RegulationChange(
        source_id=source.id,
        source_url=discovery.source_url,
        source_document_key=discovery.source_document_key,
        document_name=discovery.document_name,
        detected_at=datetime.utcnow(),
        change_type=ChangeType.UNKNOWN,
        summary_text=f"Discovery not published: {reason}",
        severity=Severity.LOW,
        status="REJECTED",
        document_type=discovery.document_type or source.doc_type,
        crawl_status=crawl_status,
        reject_reason=reason,
        review_state="rejected",
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change


def _publish_regulation_change(db: Session, change: RegulationChange) -> None:
    from app.services.llm_service import sync_regulation_change_to_kb
    from app.services.notification import send_regulation_change_email

    alert = Alert(
        regulation_change_id=change.id,
        alert_type=AlertType.REGULATION_CHANGE,
        severity=change.severity,
        title=f"Regulation Update: {change.document_name[:100]}",
        message=change.summary_text or f"New regulation document detected: {change.document_name}",
        rule_violations=[],
        status=AlertStatus.UNREAD,
    )
    db.add(alert)
    db.commit()

    try:
        sync_regulation_change_to_kb(db, change)
    except Exception as exc:
        log.warning("[regulations] KB sync failed for change %s: %s", change.id, exc)

    try:
        send_regulation_change_email(change)
    except Exception as exc:
        log.warning("[regulations] email failed for change %s: %s", change.id, exc)


def _latest_change_for_document(db: Session, source_id: int, source_document_key: str) -> RegulationChange | None:
    return (
        db.query(RegulationChange)
        .filter(
            RegulationChange.source_id == source_id,
            RegulationChange.source_document_key == source_document_key,
            RegulationChange.crawl_status == "accepted",
        )
        .order_by(RegulationChange.detected_at.desc())
        .first()
    )


def _parse_change_type(value: str | None) -> ChangeType:
    try:
        return ChangeType(value or "UNKNOWN")
    except ValueError:
        return ChangeType.UNKNOWN


def _parse_severity(value: str | None) -> Severity:
    try:
        return Severity(value or "MEDIUM")
    except ValueError:
        return Severity.MEDIUM


def _parse_effective_date(value: str | None):
    if not value:
        return None
    try:
        from dateutil import parser as dateparser

        return dateparser.parse(value)
    except Exception:
        return None


def _family_for_url(url: str) -> str:
    if "ayush" in url:
        return "ayush"
    if "consumeraffairs" in url or "legalmetrology" in url:
        return "legal_metrology"
    return "fssai"


def _safe_int(value, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _source_config(source: RegulationSource) -> dict:
    config = get_default_source_config(source.slug)
    custom = source.discovery_config or {}
    config.update(custom)
    return config
