import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, LabelVersion, Alert, AlertType, AlertStatus, CheckResult, Severity, ComplianceReport
from app.routes.auth import get_current_user_from_cookie
from app.services.ocr_service import extract_text_from_file
from app.services.extraction_service import extract_label_data
from app.services.compliance_engine import run_compliance_check, calculate_compliance_score, get_violation_summary
from app.config import get_settings

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".pdf", ".webp"}


def require_user(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None
    return user


@router.get("/products/{product_id}/upload")
async def upload_page(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    product = db.query(Product).filter(
        Product.id == product_id, Product.user_id == user.id
    ).first()
    if not product:
        return RedirectResponse(url="/products")

    return templates.TemplateResponse("label_upload.html", {
        "request": request,
        "user": user,
        "product": product,
    })


@router.post("/products/{product_id}/upload")
async def upload_label(
    product_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    product = db.query(Product).filter(
        Product.id == product_id, Product.user_id == user.id
    ).first()
    if not product:
        return RedirectResponse(url="/products")

    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return templates.TemplateResponse("label_upload.html", {
            "request": request,
            "user": user,
            "product": product,
            "error": f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        })

    # Save file
    upload_dir = Path(settings.upload_dir) / str(product_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}{suffix}"
    file_path = upload_dir / file_name

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Mark previous versions as not current
    db.query(LabelVersion).filter(
        LabelVersion.product_id == product_id, LabelVersion.is_current == True
    ).update({"is_current": False})

    # Create label version record (processing happens in background)
    label_version = LabelVersion(
        product_id=product_id,
        file_path=str(file_path),
        file_name=file.filename,
        file_type="pdf" if suffix == ".pdf" else "image",
        is_current=True,
    )
    db.add(label_version)
    db.commit()
    db.refresh(label_version)

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "label_uploaded", "label", label_version.id, detail=f"Uploaded label for {product.name}")
    except Exception:
        pass

    # Run OCR + extraction + compliance check in background
    background_tasks.add_task(_process_label, label_version.id)

    return RedirectResponse(url=f"/labels/{label_version.id}?processing=1", status_code=302)


def _process_label(label_version_id: int):
    """Background task: OCR → extract → compliance check → create alerts."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        label_version = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
        if not label_version:
            return

        # Step 1: OCR
        raw_text, _ = extract_text_from_file(label_version.file_path)
        label_version.ocr_raw_text = raw_text

        # Step 2: Structured extraction
        extraction, confidence = extract_label_data(raw_text)
        label_version.extraction_json = extraction
        label_version.extraction_confidence = confidence
        db.commit()

        # Step 3: Compliance check
        checks = run_compliance_check(label_version, db)

        # Step 4: Create alerts for CRITICAL/HIGH failures
        violations = []
        for check in checks:
            if check.result == CheckResult.FAIL and check.rule:
                violations.append({
                    "rule_code": check.rule.rule_code,
                    "field": check.rule.check_config.get("field", ""),
                    "message": check.message,
                    "remediation": check.remediation or check.rule.remediation_template,
                    "severity": check.rule.severity.value,
                })

        critical_violations = [v for v in violations if v["severity"] == "CRITICAL"]
        high_violations = [v for v in violations if v["severity"] == "HIGH"]

        if critical_violations or high_violations:
            score = calculate_compliance_score(checks)
            alert = Alert(
                product_id=label_version.product_id,
                label_version_id=label_version.id,
                alert_type=AlertType.LABEL_VIOLATION,
                severity=Severity.CRITICAL if critical_violations else Severity.HIGH,
                title=f"Label compliance issues detected — {len(violations)} violation(s)",
                message=(
                    f"Compliance score: {score}%. "
                    f"{len(critical_violations)} critical, {len(high_violations)} high severity issues found."
                ),
                rule_violations=violations,
                status=AlertStatus.UNREAD,
            )
            db.add(alert)
            db.commit()

            # Send email notification
            try:
                from app.services.notification import send_alert_email
                product = db.query(Product).filter(Product.id == label_version.product_id).first()
                send_alert_email(alert, product)
            except Exception as e:
                print(f"[alert] Email failed: {e}")

    except Exception as e:
        print(f"[process_label] Error: {e}")
        db.rollback()
    finally:
        db.close()


@router.get("/labels/{label_id}")
async def label_report(label_id: int, request: Request, processing: int = 0, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or label.product.user_id != user.id:
        return RedirectResponse(url="/products")

    _ = label.checks
    for check in label.checks:
        _ = check.rule

    score = calculate_compliance_score(label.checks) if label.checks else None
    violation_summary = get_violation_summary(label.checks) if label.checks else {}

    # Group checks by result
    failed = [c for c in label.checks if c.result == CheckResult.FAIL]
    warnings = [c for c in label.checks if c.result == CheckResult.WARNING]
    passed = [c for c in label.checks if c.result == CheckResult.PASS]

    # Try to find existing compliance report for this label version
    existing_report = db.query(ComplianceReport).filter(
        ComplianceReport.label_version_id == label_id
    ).first()

    return templates.TemplateResponse("label_report.html", {
        "request": request,
        "user": user,
        "label": label,
        "product": label.product,
        "score": score,
        "violation_summary": violation_summary,
        "failed_checks": sorted(failed, key=lambda c: c.rule.severity.value if c.rule else ""),
        "warning_checks": warnings,
        "passed_checks": passed,
        "processing": bool(processing) and not label.extraction_json,
        "CheckResult": CheckResult,
        "existing_report": existing_report,
    })
