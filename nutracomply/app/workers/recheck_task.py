"""
Re-check Task — re-runs compliance checks on all current label versions.

Triggered automatically when a CRITICAL regulation change is detected.
Can also be triggered manually from the admin panel.
"""

from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.recheck_task.recheck_all_labels", bind=True)
def recheck_all_labels(self):
    from app.database import SessionLocal
    from app.models import LabelVersion, Alert, AlertType, AlertStatus, Severity, Product, CheckResult, User
    from app.services.compliance_engine import run_compliance_check, calculate_compliance_score
    from app.services.notification import send_alert_email

    db = SessionLocal()
    rechecked = 0
    new_failures = 0

    try:
        # Get all current label versions that have already been processed
        current_labels = (
            db.query(LabelVersion)
            .filter(
                LabelVersion.is_current == True,
                LabelVersion.extraction_json is not None,
            )
            .all()
        )

        print(f"[recheck] Re-checking {len(current_labels)} current labels")

        for label in current_labels:
            prev_checks = list(label.checks)
            prev_score = calculate_compliance_score(prev_checks) if prev_checks else None

            # Run fresh compliance check
            new_checks = run_compliance_check(label, db)
            new_score = calculate_compliance_score(new_checks)

            # Detect regressions (previously passing, now failing)
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
                        f"A recent FSSAI regulation change has made this label non-compliant. "
                        f"Score changed from {prev_score}% to {new_score}%. "
                        f"{len(now_failing)} new violation(s) detected."
                    ),
                    rule_violations=violations,
                    status=AlertStatus.UNREAD,
                )
                db.add(alert)
                db.commit()

                try:
                    from app.services.access_control import get_account_contact_user

                    owner = (
                        get_account_contact_user(db, product.account_id) if product else None
                    ) or (product.owner if product else None)
                    send_alert_email(alert, product, user=owner)
                except Exception as e:
                    print(f"[recheck] Email failed: {e}")

            rechecked += 1

        print(f"[recheck] Done. {rechecked} labels re-checked, {new_failures} new failures.")
        return {"rechecked": rechecked, "new_failures": new_failures}

    except Exception as e:
        db.rollback()
        print(f"[recheck] Error: {e}")
        raise
    finally:
        db.close()
