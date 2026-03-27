"""
In-Process Daily Scheduler
===========================
Replaces Celery Beat + Redis dependency with a lightweight threading-based
scheduler that runs inside the main FastAPI process.

Tasks:
  1. Daily FSSAI/AYUSH/LM/eGazette regulation scraping (6:00 AM IST)
  2. Auto-reseed LLM KB after new regulation data is detected
  3. License expiry reminder emails (7:00 AM IST daily)
  4. Auto-rule update suggestions on CRITICAL changes

Runs in a daemon thread — exits automatically when the main process stops.
"""

import threading
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

# Track whether the scheduler is already running (prevent double-start)
_scheduler_started = False
_scheduler_lock = threading.Lock()


def start_scheduler():
    """Start the background scheduler thread. Safe to call multiple times."""
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    t = threading.Thread(target=_scheduler_loop, daemon=True, name="regbite-scheduler")
    t.start()
    print("[scheduler] Started daily regulation scheduler")


def _scheduler_loop():
    """Main scheduler loop — checks every 60 seconds if any task is due."""
    last_scrape_date = None
    last_expiry_date = None

    # Wait 30 seconds after startup before first check (let DB init finish)
    time.sleep(30)

    while True:
        try:
            now_ist = datetime.now(IST)
            today = now_ist.date()

            # Task 1: Daily regulation scrape at 6:00 AM IST
            if now_ist.hour == 6 and last_scrape_date != today:
                last_scrape_date = today
                print(f"[scheduler] Starting daily regulation scrape at {now_ist}")
                _run_scrape_task()

            # Task 2: License expiry reminders at 7:00 AM IST
            if now_ist.hour == 7 and last_expiry_date != today:
                last_expiry_date = today
                print(f"[scheduler] Checking license expiry reminders at {now_ist}")
                _run_expiry_reminders()

        except Exception as e:
            print(f"[scheduler] Error in scheduler loop: {e}")

        # Sleep 60 seconds between checks
        time.sleep(60)


def _run_scrape_task():
    """Run the regulation scraping pipeline (mirrors scrape_task.py logic without Celery)."""
    from app.database import SessionLocal
    from app.models import (
        RegulationChange, ChangeType, Severity, Alert, AlertType, AlertStatus,
        RegulationStatus,
    )
    from app.services.scraper import (
        scrape_fssai_pages, download_and_hash, classify_regulation_change,
        suggest_rule_modifications,
    )

    db = SessionLocal()
    new_changes = []

    try:
        documents = scrape_fssai_pages()
        print(f"[scheduler] Found {len(documents)} documents to check")

        for doc in documents:
            url = doc["source_url"]
            name = doc["document_name"]

            # Check if we've seen this URL before
            existing = db.query(RegulationChange).filter(
                RegulationChange.source_url == url
            ).order_by(RegulationChange.detected_at.desc()).first()

            # Download and hash
            text, new_hash = download_and_hash(url)
            if not new_hash:
                continue

            # Compare hash — skip if unchanged
            if existing and existing.document_hash == new_hash:
                continue

            print(f"[scheduler] New/changed document: {name}")

            # Classify the change
            classification = classify_regulation_change(name, text or "")

            try:
                change_type = ChangeType(classification.get("change_type", "UNKNOWN"))
            except ValueError:
                change_type = ChangeType.UNKNOWN

            try:
                severity = Severity(classification.get("severity", "MEDIUM"))
            except ValueError:
                severity = Severity.MEDIUM

            # Parse effective date
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

            # Create in-app alert
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

            # Send email notification
            try:
                from app.services.notification import send_regulation_change_email
                send_regulation_change_email(change)
            except Exception as e:
                print(f"[scheduler] Email notification failed: {e}")

        print(f"[scheduler] Scrape done. {len(new_changes)} new changes detected.")

        # If there are critical changes, trigger label re-checks + rule suggestions
        critical_changes = [c for c in new_changes if c.severity.value == "CRITICAL"]
        if critical_changes:
            _run_recheck(db)
            _suggest_rule_updates(db, critical_changes)

        # If any new changes detected, auto-reseed LLM KB
        if new_changes:
            _reseed_llm_kb(db)

    except Exception as e:
        db.rollback()
        print(f"[scheduler] Scrape error: {e}")
    finally:
        db.close()


def _run_recheck(db):
    """Re-check all current labels against updated rules."""
    from app.models import (
        LabelVersion, Alert, AlertType, AlertStatus, Severity,
        Product, CheckResult, User,
    )
    from app.services.compliance_engine import run_compliance_check, calculate_compliance_score

    try:
        current_labels = (
            db.query(LabelVersion)
            .filter(
                LabelVersion.is_current == True,
                LabelVersion.extraction_json != None,
            )
            .all()
        )

        print(f"[scheduler] Re-checking {len(current_labels)} current labels")
        rechecked = 0
        new_failures = 0

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
                    title=f"Label non-compliant after regulation update — {product.name if product else ''}",
                    message=(
                        f"A regulation change has made this label non-compliant. "
                        f"Score: {prev_score}% → {new_score}%. "
                        f"{len(now_failing)} new violation(s)."
                    ),
                    rule_violations=violations,
                    status=AlertStatus.UNREAD,
                )
                db.add(alert)
                db.commit()

                # Send email to product owner
                try:
                    from app.services.notification import send_alert_email
                    owner = db.query(User).filter(User.id == product.user_id).first() if product else None
                    send_alert_email(alert, product, user=owner)
                except Exception as e:
                    print(f"[scheduler] Alert email failed: {e}")

            rechecked += 1

        print(f"[scheduler] Re-check done. {rechecked} labels, {new_failures} new failures.")
    except Exception as e:
        print(f"[scheduler] Re-check error: {e}")


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
                print(f"[scheduler] Rule suggestions for '{change.document_name[:60]}': {len(suggestions)} changes proposed")
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
                        link="/admin/regulations-kb/",
                    )
    except Exception as e:
        print(f"[scheduler] Rule suggestion error: {e}")


def _reseed_llm_kb(db):
    """Auto-reseed the Regulations LLM KB after new data arrives."""
    try:
        from app.services.llm_service import seed_regulations_kb
        result = seed_regulations_kb(db)
        print(f"[scheduler] LLM KB re-seeded: {result.get('document_count', 0)} documents")
    except Exception as e:
        print(f"[scheduler] LLM KB reseed error: {e}")


def _run_expiry_reminders():
    """Send license expiry reminder emails for licenses expiring within 30 days."""
    from app.database import SessionLocal
    from app.models import LicenseRenewal, User

    db = SessionLocal()
    try:
        # Find non-perpetual licenses expiring within 30 days
        cutoff = datetime.utcnow() + timedelta(days=30)
        expiring = (
            db.query(LicenseRenewal)
            .filter(
                LicenseRenewal.is_active == True,
                LicenseRenewal.is_perpetual == False,
                LicenseRenewal.expiry_date <= cutoff,
                LicenseRenewal.expiry_date >= datetime.utcnow(),
            )
            .all()
        )

        if not expiring:
            print("[scheduler] No expiring licenses found")
            return

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
                from app.services.notification import send_license_expiry_email
                send_license_expiry_email(user, licenses)
                sent += 1
            except Exception as e:
                print(f"[scheduler] Expiry email failed for user {user_id}: {e}")

        print(f"[scheduler] Sent {sent} license expiry reminders")
    except Exception as e:
        print(f"[scheduler] Expiry reminder error: {e}")
    finally:
        db.close()
