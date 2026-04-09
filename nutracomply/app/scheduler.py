"""
In-process daily scheduler — runs inside the main FastAPI process.

Replaces the Celery Beat + Redis dependency for Railway deployment where
only a single web process runs. Uses a daemon thread with time.sleep().

Scheduled jobs:
  1. Daily FSSAI/AYUSH/LM/eGazette regulation scrape (6:00 AM IST = 00:30 UTC)
  2. Auto-reseed LLM KB after new regulation data is detected
  3. License expiry reminder emails (7:00 AM IST = 01:30 UTC)
  4. Auto-rule update suggestions on CRITICAL changes
"""

import threading
import time
from datetime import datetime, timedelta

import logging

log = logging.getLogger("regbite.scheduler")

_scheduler_started = False
_lock = threading.Lock()


def _next_run_utc(hour_utc: int, minute_utc: int) -> datetime:
    """Return the next occurrence of HH:MM UTC (today or tomorrow)."""
    now = datetime.utcnow()
    target = now.replace(hour=hour_utc, minute=minute_utc, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _run_daily_scrape():
    """Run the FSSAI regulation scraper (same logic as the Celery task)."""
    from app.database import SessionLocal
    from app.models import (
        RegulationChange, ChangeType, Severity, Alert, AlertType, AlertStatus,
        RegulationStatus,
    )

    db = SessionLocal()
    new_changes = []

    try:
        from app.services.scraper import (
            scrape_fssai_pages, download_and_hash, classify_regulation_change,
        )
        from app.services.notification import send_regulation_change_email

        log.info("[scheduler] Starting daily FSSAI scrape")
        documents = scrape_fssai_pages()
        log.info("[scheduler] Found %d documents to check", len(documents))

        for doc in documents:
            url = doc["source_url"]
            name = doc["document_name"]

            existing = db.query(RegulationChange).filter(
                RegulationChange.source_url == url
            ).order_by(RegulationChange.detected_at.desc()).first()

            text, new_hash = download_and_hash(url)
            if not new_hash:
                continue

            if existing and existing.document_hash == new_hash:
                continue

            log.info("[scheduler] New/changed document: %s", name)

            classification = classify_regulation_change(name, text or "")

            try:
                change_type = ChangeType(classification.get("change_type", "UNKNOWN"))
            except ValueError:
                change_type = ChangeType.UNKNOWN

            try:
                severity = Severity(classification.get("severity", "MEDIUM"))
            except ValueError:
                severity = Severity.MEDIUM

            effective_date = None
            if classification.get("effective_date"):
                try:
                    from dateutil import parser as dateparser
                    effective_date = dateparser.parse(classification["effective_date"])
                except Exception:
                    pass

            change = RegulationChange(
                source_url=url,
                document_name=name,
                detected_at=datetime.utcnow(),
                change_type=change_type,
                summary_text=classification.get("summary_text", ""),
                diff_text=(text or "")[:2000],
                effective_date=effective_date,
                severity=severity,
                document_hash=new_hash,
                status="NEW",
                regulation_status=RegulationStatus.EFFECTIVE,
            )
            db.add(change)
            db.commit()
            db.refresh(change)
            new_changes.append(change)

            alert = Alert(
                regulation_change_id=change.id,
                alert_type=AlertType.REGULATION_CHANGE,
                severity=severity,
                title=f"Regulation Update: {change_type.value} — {name[:100]}",
                message=classification.get("summary_text", f"New/updated document detected: {name}"),
                rule_violations=[],
                status=AlertStatus.UNREAD,
            )
            db.add(alert)
            db.commit()

            try:
                send_regulation_change_email(change)
            except Exception as e:
                log.warning("[scheduler] Email notification failed: %s", e)

        log.info("[scheduler] Scrape done. %d new changes detected.", len(new_changes))

        # If there are critical changes, trigger label re-checks + rule suggestions
        critical_changes = [c for c in new_changes if c.severity.value == "CRITICAL"]
        if critical_changes:
            log.info("[scheduler] %d CRITICAL changes — triggering label re-check", len(critical_changes))
            _run_recheck()
            _suggest_rule_updates(db, critical_changes)

        # If any new changes detected, auto-reseed LLM KB
        if new_changes:
            _reseed_llm_kb(db)

    except Exception as e:
        db.rollback()
        log.error("[scheduler] Scrape error: %s", e)
    finally:
        db.close()


def _run_recheck():
    """Re-check all current labels (same logic as the Celery recheck task)."""
    from app.database import SessionLocal
    from app.models import LabelVersion, Alert, AlertType, AlertStatus, Severity, Product, CheckResult, User
    from app.services.compliance_engine import run_compliance_check, calculate_compliance_score
    from app.services.notification import send_alert_email

    db = SessionLocal()
    rechecked = 0
    new_failures = 0

    try:
        current_labels = (
            db.query(LabelVersion)
            .filter(
                LabelVersion.is_current == True,
                LabelVersion.extraction_json != None,
            )
            .all()
        )

        log.info("[scheduler] Re-checking %d current labels", len(current_labels))

        for label in current_labels:
            prev_checks = list(label.checks)
            prev_score = calculate_compliance_score(prev_checks) if prev_checks else None

            new_checks = run_compliance_check(label, db)
            new_score = calculate_compliance_score(new_checks)

            prev_passed_codes = {
                c.rule.rule_code for c in prev_checks
                if c.result == CheckResult.PASS and c.rule
            }
            now_failing = [
                c for c in new_checks
                if c.result == CheckResult.FAIL and c.rule
                and c.rule.rule_code in prev_passed_codes
            ]

            if now_failing:
                new_failures += len(now_failing)
                violations = [
                    {
                        "rule_code": c.rule.rule_code,
                        "field": c.rule.check_config.get("field", ""),
                        "message": c.message,
                        "remediation": c.remediation or c.rule.remediation_template,
                        "severity": c.rule.severity.value,
                    }
                    for c in now_failing
                ]

                product = db.query(Product).filter(Product.id == label.product_id).first()
                alert = Alert(
                    product_id=label.product_id,
                    label_version_id=label.id,
                    alert_type=AlertType.LABEL_VIOLATION,
                    severity=Severity.HIGH,
                    title=f"Label now non-compliant after regulation update — {product.name if product else ''}",
                    message=(
                        f"A recent regulation change has made this label non-compliant. "
                        f"Score changed from {prev_score}% to {new_score}%. "
                        f"{len(now_failing)} new violation(s) detected."
                    ),
                    rule_violations=violations,
                    status=AlertStatus.UNREAD,
                )
                db.add(alert)
                db.commit()

                try:
                    owner = db.query(User).filter(User.id == product.user_id).first() if product else None
                    send_alert_email(alert, product, user=owner)
                except Exception as e:
                    log.warning("[scheduler] Recheck email failed: %s", e)

            rechecked += 1

        log.info("[scheduler] Recheck done. %d labels, %d new failures.", rechecked, new_failures)

    except Exception as e:
        db.rollback()
        log.error("[scheduler] Recheck error: %s", e)
    finally:
        db.close()


def _suggest_rule_updates(db, critical_changes):
    """Use LLM to suggest rule modifications for CRITICAL changes."""
    from app.models import ComplianceRule
    from app.services.scraper import suggest_rule_modifications

    try:
        existing_rules = [
            {"rule_code": r.rule_code, "description": r.description}
            for r in db.query(ComplianceRule).filter(ComplianceRule.active == True).all()
        ]

        for change in critical_changes:
            suggestions = suggest_rule_modifications(
                change.document_name,
                change.diff_text or change.summary_text or "",
                existing_rules,
            )
            if suggestions:
                log.info("[scheduler] Rule suggestions for '%s': %d changes proposed",
                         change.document_name[:60], len(suggestions))
                # Store suggestions as a notification for admin review
                from app.services.notify_service import push
                from app.models import User
                admins = db.query(User).filter(User.is_admin == True).all()
                for admin in admins:
                    push(
                        admin.id,
                        title=f"Rule update suggested: {change.document_name[:80]}",
                        message=f"{len(suggestions)} rule changes suggested by AI. Review in admin panel.",
                        ntype="alert",
                        link="/admin/llm/regulations/train",
                    )
    except Exception as e:
        log.error("[scheduler] Rule suggestion error: %s", e)


def _reseed_llm_kb(db):
    """Auto-reseed the Regulations LLM KB after new data arrives."""
    try:
        from app.services.llm_service import seed_regulations_kb
        result = seed_regulations_kb(db)
        log.info("[scheduler] LLM KB re-seeded: %d documents", result.get('document_count', 0))
    except Exception as e:
        log.error("[scheduler] LLM KB reseed error: %s", e)


def _run_license_expiry_reminders():
    """Send reminder emails for licenses expiring in the next 30 days."""
    from app.database import SessionLocal
    from app.models import LicenseRenewal, User

    db = SessionLocal()

    try:
        from app.services.notification import send_license_expiry_email

        cutoff = datetime.utcnow() + timedelta(days=30)
        expiring = (
            db.query(LicenseRenewal)
            .filter(
                LicenseRenewal.is_active == True,
                LicenseRenewal.is_perpetual == False,
                LicenseRenewal.expiry_date <= cutoff,
                LicenseRenewal.expiry_date > datetime.utcnow(),
            )
            .all()
        )

        log.info("[scheduler] Found %d licenses expiring within 30 days", len(expiring))

        # Group by user
        by_user: dict[int, list] = {}
        for lic in expiring:
            by_user.setdefault(lic.user_id, []).append(lic)

        sent = 0
        for user_id, licenses in by_user.items():
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                continue

            try:
                send_license_expiry_email(user, licenses)
                sent += 1
            except Exception as e:
                log.warning("[scheduler] License expiry email failed for user %s: %s", user_id, e)

        log.info("[scheduler] Sent %d license expiry reminders", sent)

    except Exception as e:
        log.error("[scheduler] License expiry error: %s", e)
    finally:
        db.close()


def _scheduler_loop():
    """
    Main scheduler loop. Sleeps until the next scheduled time, runs the job,
    then sleeps until the next day's run.
    """
    # Schedule: daily scrape at 00:30 UTC (6:00 AM IST)
    #           license reminders at 01:30 UTC (7:00 AM IST)
    while True:
        try:
            now = datetime.utcnow()

            # Calculate next scrape time (00:30 UTC)
            next_scrape = _next_run_utc(0, 30)
            # Calculate next license reminder time (01:30 UTC)
            next_license = _next_run_utc(1, 30)

            # Find the nearest job
            next_job_time = min(next_scrape, next_license)
            sleep_seconds = (next_job_time - now).total_seconds()

            log.info(
                "[scheduler] Next job at %s UTC (in %.0f minutes)",
                next_job_time.strftime("%Y-%m-%d %H:%M"),
                sleep_seconds / 60,
            )

            time.sleep(max(sleep_seconds, 60))  # minimum 60s to avoid tight loops

            # After sleeping, check which jobs are due (within 5-min window)
            now = datetime.utcnow()

            # Check if scrape is due (00:30 UTC, within 5-min window)
            scrape_target = now.replace(hour=0, minute=30, second=0, microsecond=0)
            if abs((now - scrape_target).total_seconds()) < 300:
                log.info("[scheduler] Running daily regulation scrape")
                try:
                    _run_daily_scrape()
                except Exception as e:
                    log.error("[scheduler] Daily scrape failed: %s", e)

            # Check if license reminders are due (01:30 UTC, within 5-min window)
            license_target = now.replace(hour=1, minute=30, second=0, microsecond=0)
            if abs((now - license_target).total_seconds()) < 300:
                log.info("[scheduler] Running license expiry reminders")
                try:
                    _run_license_expiry_reminders()
                except Exception as e:
                    log.error("[scheduler] License reminders failed: %s", e)

        except Exception as e:
            log.error("[scheduler] Loop error: %s", e)
            time.sleep(300)  # sleep 5 min on unexpected error


def start_scheduler():
    """Start the background scheduler thread (idempotent — only starts once)."""
    global _scheduler_started
    with _lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="regbite-scheduler")
    thread.start()
    log.info("[scheduler] Daily scheduler started (scrape 00:30 UTC, license reminders 01:30 UTC)")
