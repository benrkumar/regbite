"""
Daily regulation crawl task

Runs the shared source-registry regulation ingestion pipeline and returns
freshness / publication results.
"""

from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.scrape_task.run_fssai_scrape", bind=True, max_retries=3)
def run_fssai_scrape(self):
    from app.database import SessionLocal
    from app.services.regulation_ingestion import crawl_active_regulation_sources

    db = SessionLocal()

    try:
        result = crawl_active_regulation_sources(db, initiated_by="celery")
        print(
            f"[scraper] Regulation crawl complete: "
            f"{result['accepted_count']} accepted, "
            f"{result['reject_count']} rejected, "
            f"{result['unchanged_count']} unchanged"
        )

        critical_changes = [
            change
            for change in result["accepted_changes"]
            if getattr(change.severity, "value", change.severity) == "CRITICAL"
        ]
        if critical_changes:
            from app.workers.recheck_task import recheck_all_labels

            recheck_all_labels.delay()

        return {
            "accepted_changes": result["accepted_count"],
            "rejected_changes": result["reject_count"],
            "unchanged_changes": result["unchanged_count"],
        }

    except Exception as exc:
        db.rollback()
        print(f"[scraper] Error: {exc}")
        raise self.retry(exc=exc, countdown=300)
    finally:
        db.close()
