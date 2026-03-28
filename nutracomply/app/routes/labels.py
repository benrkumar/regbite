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
from app.services.extraction_service import extract_label_data, extract_label_data_from_image
from app.services.compliance_engine import run_compliance_check, calculate_compliance_score, calculate_critical_score, get_violation_summary
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

    try:
        from app.services.rate_limiter import limiter
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check("upload", client_ip, limit=30, window=3600)  # 30/hr
        if not allowed:
            return RedirectResponse(url=f"/products?error=Upload+rate+limit+exceeded.", status_code=302)
    except Exception:
        pass

    # Quota check
    try:
        from app.services.quota_service import check_scan_limit
        allowed, quota_msg = check_scan_limit(user, db)
        if not allowed:
            from urllib.parse import quote
            return RedirectResponse(url=f"/products/{product_id}?msg={quote(quota_msg)}&type=error", status_code=302)
    except Exception:
        pass

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

    # Read file with size limit (50 MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return templates.TemplateResponse("label_upload.html", {
            "request": request,
            "user": user,
            "product": product,
            "error": "File too large. Maximum size is 50 MB."
        })

    # Validate MIME type via file magic bytes
    MAGIC_SIGNATURES = {
        b"\xff\xd8\xff": ".jpg",       # JPEG
        b"\x89PNG\r\n\x1a\n": ".png",  # PNG
        b"%PDF": ".pdf",               # PDF
        b"II\x2a\x00": ".tiff",        # TIFF (little-endian)
        b"MM\x00\x2a": ".tiff",        # TIFF (big-endian)
        b"RIFF": ".webp",              # WebP (inside RIFF container)
    }
    detected_ext = None
    for sig, ext in MAGIC_SIGNATURES.items():
        if content[:len(sig)] == sig:
            detected_ext = ext
            break
    if detected_ext is None:
        return templates.TemplateResponse("label_upload.html", {
            "request": request,
            "user": user,
            "product": product,
            "error": "File content doesn't match a supported image or PDF format."
        })

    # Save file
    upload_dir = Path(settings.upload_dir) / str(product_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}{suffix}"
    file_path = upload_dir / file_name

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
    """Background task: OCR → extract → compliance check → create alerts.

    Token-saving: If a previous extraction with confidence >= 0.85 exists,
    skip the Gemini API call and re-use the stored extraction data.
    Only re-runs the compliance rules engine (zero API tokens).
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        label_version = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
        if not label_version:
            return

        # Check if we can re-use existing high-confidence extraction (saves tokens)
        reuse_extraction = (
            label_version.extraction_json
            and label_version.extraction_confidence
            and label_version.extraction_confidence >= 0.85
        )

        if reuse_extraction:
            print(f"[process_label] Re-using cached extraction (confidence={label_version.extraction_confidence}) — 0 API tokens")
            extraction = label_version.extraction_json
        else:
            # Step 1: OCR
            raw_text, _ = extract_text_from_file(label_version.file_path)
            label_version.ocr_raw_text = raw_text

            # Step 2: Structured extraction — try Vision API first for images
            extraction = None
            confidence = 0.0
            if label_version.file_type == "image":
                try:
                    extraction, confidence = extract_label_data_from_image(label_version.file_path)
                except Exception as e:
                    print(f"[extraction] Vision fallback: {e}")

            if not extraction or confidence < 0.5:
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

            # Send email notification to product owner
            try:
                from app.services.notification import send_alert_email
                from app.models import User
                product = db.query(Product).filter(Product.id == label_version.product_id).first()
                owner = db.query(User).filter(User.id == product.user_id).first() if product else None
                send_alert_email(alert, product, user=owner)
            except Exception as e:
                print(f"[alert] Email failed: {e}")

        # Step 5: Feed product into LLM knowledge base
        try:
            from app.routes.products import _feed_product_to_llm
            _feed_product_to_llm(label_version.product_id, db)
        except Exception as e:
            print(f"[llm-feed] Error: {e}")

    except Exception as e:
        print(f"[process_label] Error: {e}")
        db.rollback()
    finally:
        db.close()


@router.post("/labels/{label_id}/reanalyze")
async def reanalyze_label(
    label_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Re-run compliance check on an existing label.

    Token-saving: If the label already has a high-confidence extraction
    (>= 0.85), only re-runs the rules engine — zero Gemini API tokens.
    Pass ?force_extract=1 to force a fresh Vision/OCR extraction.
    """
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or label.product.user_id != user.id:
        return RedirectResponse(url="/products")

    force_extract = request.query_params.get("force_extract") == "1"

    if force_extract or not label.extraction_json or (label.extraction_confidence or 0) < 0.85:
        # Clear extraction to trigger fresh Vision/OCR extraction
        label.extraction_json = None
        label.extraction_confidence = None
        db.commit()

    background_tasks.add_task(_process_label, label.id)
    return RedirectResponse(url=f"/labels/{label.id}?processing=1", status_code=302)


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
    critical = calculate_critical_score(label.checks) if label.checks else {"critical_pass": True, "critical_score": 100, "critical_failures": 0}
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
        "critical": critical,
        "violation_summary": violation_summary,
        "failed_checks": sorted(failed, key=lambda c: c.rule.severity.value if c.rule else ""),
        "warning_checks": warnings,
        "passed_checks": passed,
        "processing": bool(processing) and not label.extraction_json,
        "CheckResult": CheckResult,
        "existing_report": existing_report,
    })
