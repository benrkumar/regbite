"""
Daily FSSAI Scrape Task

Runs at 00:30 IST every day.
1. Fetches regulation + advisory pages
2. Downloads each linked PDF, computes SHA-256
3. Compares against stored hashes in DB
4. For new/changed documents: classify with LLM, save RegulationChange, trigger re-check
"""

from datetime import datetime
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.scrape_task.run_fssai_scrape", bind=True, max_retries=3)
def run_fssai_scrape(self):
    from app.database import SessionLocal
    from app.models import RegulationChange, ChangeType, Severity, Alert, AlertType, AlertStatus
    from app.services.scraper import (
        scrape_fssai_pages, download_and_hash, classify_regulation_change
    )
    from app.services.notification import send_regulation_change_email

    db = SessionLocal()
    new_changes = []

    try:
        print(f"[scraper] Starting FSSAI scrape at {datetime.utcnow()}")
        documents = scrape_fssai_pages()
        print(f"[scraper] Found {len(documents)} documents to check")

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

            print(f"[scraper] New/changed document: {name}")

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
                title=f"FSSAI Regulation Update: {change_type.value} — {name[:100]}",
                message=classification.get("summary_text", f"New/updated document detected: {name}"),
                rule_violations=[],
                status=AlertStatus.UNREAD,
            )
            db.add(alert)
            db.commit()

            # Send email notification
            try:
                send_regulation_change_email(change)
            except Exception as e:
                print(f"[scraper] Email notification failed: {e}")

        print(f"[scraper] Done. {len(new_changes)} new changes detected.")

        # If there are critical changes, trigger label re-checks
        critical_changes = [c for c in new_changes if c.severity.value == "CRITICAL"]
        if critical_changes:
            from app.workers.recheck_task import recheck_all_labels
            recheck_all_labels.delay()

        return {"new_changes": len(new_changes)}

    except Exception as exc:
        db.rollback()
        print(f"[scraper] Error: {exc}")
        raise self.retry(exc=exc, countdown=300)
    finally:
        db.close()
