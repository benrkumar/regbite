import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, LabelVersion, ComplianceCheck, Alert, AlertType, AlertStatus, CheckResult, Severity, ComplianceReport
from app.routes.auth import get_current_user_from_cookie
from app.services.ocr_service import extract_text_from_file
from app.services.extraction_service import extract_label_data, extract_label_data_from_image, _cross_check_with_ocr
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
        return RedirectResponse(url="/login", status_code=302)

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
        return RedirectResponse(url="/login", status_code=302)

    try:
        from app.services.rate_limiter import limiter
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check("upload", client_ip, limit=30, window=3600)  # 30/hr
        if not allowed:
            return RedirectResponse(url="/products?error=Upload+rate+limit+exceeded.", status_code=302)
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
    """Background task: Claude Vision → compliance check → create alerts.

    Fast path (default, ~20-25s):
      Claude Vision reads the image or PDF directly — no OCR needed.
      Returns structured JSON in one API call.

    Fallback path (~5-10s extra, only if Vision fails):
      pytesseract OCR → local pattern library → Claude Text.
      PaddleOCR removed (was causing 15-25s startup overhead every call).

    Pattern learning runs in a daemon thread — does not block compliance check.
    Token reuse: if previous extraction has confidence >= 0.85, skip extraction entirely.
    """
    import os
    import threading
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        label_version = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
        if not label_version:
            return

        # ── Cache reuse: re-run rules only on high-confidence previous extractions ──
        reuse_extraction = (
            label_version.extraction_json
            and label_version.extraction_confidence
            and label_version.extraction_confidence >= 0.85
        )

        if reuse_extraction:
            print(f"[process_label] Re-using cached extraction "
                  f"(confidence={label_version.extraction_confidence:.2f}) — 0 API tokens", flush=True)
            extraction = label_version.extraction_json
        else:
            from app.config import get_settings as _get_settings
            _cfg = _get_settings()

            # Ensure Anthropic key is reachable in subprocess/thread env
            if _cfg.anthropic_api_key:
                os.environ.setdefault("ANTHROPIC_API_KEY", _cfg.anthropic_api_key)

            extraction  = None
            confidence  = 0.0
            extr_source = "fallback"
            inp_tokens  = out_tokens = 0
            raw_text    = None   # only populated if Vision fails

            # ── FAST PATH: Claude Vision reads image/PDF directly ─────────────────
            # No OCR step — Claude sees the pixels. Typical time: 15-25s.
            try:
                extraction, confidence, extr_source, inp_tokens, out_tokens = \
                    extract_label_data_from_image(label_version.file_path)
                print(f"[process_label] Vision OK: source={extr_source} "
                      f"confidence={confidence:.2f} tokens=in:{inp_tokens} out:{out_tokens}", flush=True)
            except Exception as e:
                print(f"[process_label] Vision extraction failed: {e}", flush=True)
                extraction = None

            vision_ok = bool(extraction) and confidence >= 0.45

            # ── FALLBACK: OCR (pytesseract) → local patterns → Claude Text ────────
            if not vision_ok:
                print("[process_label] Vision failed/low-confidence — running OCR fallback", flush=True)

                try:
                    raw_text, _ = extract_text_from_file(label_version.file_path)
                    label_version.ocr_raw_text = raw_text
                    print(f"[process_label] OCR got {len(raw_text or '')} chars", flush=True)
                except Exception as e:
                    print(f"[process_label] OCR failed: {e}", flush=True)
                    raw_text = ""

                # Local pattern library (zero API cost, fast regex)
                used_local = False
                if raw_text:
                    try:
                        from app.services.local_extraction_service import extract_locally
                        local_result, local_conf = extract_locally(raw_text, db=db)
                        if _cfg.local_extraction_enabled and local_conf >= _cfg.local_extraction_min_confidence:
                            print(f"[local-extract] confidence={local_conf:.3f} — using local", flush=True)
                            extraction  = local_result
                            confidence  = local_conf
                            extr_source = "local"
                            used_local  = True
                        else:
                            print(f"[local-extract] confidence={local_conf:.3f} — falling back to Claude Text", flush=True)
                    except Exception as e:
                        print(f"[local-extract] Error: {e}", flush=True)

                # Claude Text on OCR output
                if not used_local and raw_text:
                    try:
                        extraction, confidence, extr_source, inp_tokens, out_tokens = \
                            extract_label_data(raw_text)
                        # Cross-check text extraction against raw OCR for missed fields
                        if extraction and raw_text:
                            extraction = _cross_check_with_ocr(extraction, raw_text)
                        print(f"[process_label] Text extraction: source={extr_source} "
                              f"confidence={confidence:.2f}", flush=True)
                    except Exception as e:
                        print(f"[process_label] Text extraction failed: {e}", flush=True)

            if not extraction:
                extraction = {}

            # ── Persist extraction results ────────────────────────────────────────
            label_version.extraction_json       = extraction
            label_version.extraction_confidence = confidence
            label_version.extraction_source     = extr_source
            label_version.tokens_input          = inp_tokens
            label_version.tokens_output         = out_tokens
            db.commit()

            # ── Pattern learning in daemon thread (non-blocking) ──────────────────
            # Requires OCR text — skipped on Vision success path (no raw_text available).
            # Uses own DB session so parent session can close safely.
            if extraction and confidence >= 0.80 and raw_text and extr_source in ("claude", "gemini"):
                _ext_snap  = dict(extraction)
                _text_snap = raw_text
                _lv_id     = label_version.id
                _conf_snap = confidence

                def _learn_async():
                    _db = SessionLocal()
                    try:
                        from app.services.pattern_library import learn_from_extraction
                        learn_from_extraction(_ext_snap, _text_snap, _lv_id, _db, _conf_snap)
                    except Exception as e:
                        print(f"[pattern-library] Learn failed: {e}", flush=True)
                    finally:
                        _db.close()

                threading.Thread(target=_learn_async, daemon=True).start()

        # ── Compliance check ───────────────────────────────────────────────────────
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

        # Step 5+6: KB updates — run in daemon thread (non-critical, can't block the scan result)
        _pid = label_version.product_id

        def _kb_update():
            from app.database import SessionLocal as _SL
            _db = _SL()
            try:
                from app.services.llm_service import seed_products_kb, invalidate_cache
                seed_products_kb(_db, force_update_product_id=_pid)
                invalidate_cache("products")
                print(f"[llm-kb] Products KB refreshed for product {_pid}", flush=True)
            except Exception as e:
                print(f"[llm-kb] KB refresh failed (non-critical): {e}", flush=True)
            try:
                from app.routes.products import _feed_product_to_llm
                _feed_product_to_llm(_pid, _db)
            except Exception as e:
                print(f"[llm-feed] Error: {e}", flush=True)
            finally:
                _db.close()

        threading.Thread(target=_kb_update, daemon=True).start()

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
        return RedirectResponse(url="/login", status_code=302)

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or not label.product or label.product.user_id != user.id:
        return RedirectResponse(url="/products")

    force_extract = request.query_params.get("force_extract") == "1"

    if force_extract or not label.extraction_json or (label.extraction_confidence or 0) < 0.85:
        # Clear extraction to trigger fresh Vision/OCR extraction
        label.extraction_json = None
        label.extraction_confidence = None
        db.commit()

    background_tasks.add_task(_process_label, label.id)
    return RedirectResponse(url=f"/labels/{label.id}?processing=1", status_code=302)


@router.get("/labels/{label_id}/status")
async def label_status(label_id: int, request: Request, db: Session = Depends(get_db)):
    """JSON polling endpoint — returns {ready: bool, failed: bool} for the progress bar."""
    import datetime
    user = require_user(request, db)
    if not user:
        return JSONResponse({"ready": False, "failed": False})
    # Single query with JOIN — avoids lazy-load round-trips on label.product / label.checks
    row = (
        db.query(LabelVersion, Product)
        .join(Product, Product.id == LabelVersion.product_id)
        .filter(LabelVersion.id == label_id, Product.user_id == user.id)
        .first()
    )
    if not row:
        return JSONResponse({"ready": False, "failed": True})
    label, _ = row
    has_checks = db.query(ComplianceCheck.id).filter(
        ComplianceCheck.label_version_id == label_id
    ).first() is not None

    # BUG FIX: bool({}) == False — empty dict from failed extraction locked page forever.
    # Use `is not None` so the page loads even when extraction returned no fields.
    extraction_done = label.extraction_json is not None
    ready = extraction_done and has_checks

    # Detect stuck jobs: if still not ready after 3 minutes, surface a failure
    failed = False
    if not ready and label.uploaded_at:
        age_secs = (datetime.datetime.utcnow() - label.uploaded_at).total_seconds()
        if age_secs > 180:  # 3 minutes (Haiku should finish in < 15s)
            failed = True

    return JSONResponse({"ready": ready, "failed": failed})


@router.get("/labels/{label_id}")
async def label_report(label_id: int, request: Request, processing: int = 0, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or not label.product or label.product.user_id != user.id:
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
        "failed_checks": sorted(failed, key=lambda c: c.rule.severity.value if c.rule else "zzz"),
        "warning_checks": warnings,
        "passed_checks": passed,
        "processing": bool(processing) and not label.extraction_json,
        "CheckResult": CheckResult,
        "existing_report": existing_report,
    })


@router.get("/labels/{label_id}/preview-page/{page_num}")
async def label_preview_page(label_id: int, page_num: int = 0, request: Request = None, db: Session = Depends(get_db)):
    """Serve a PDF page as a PNG image for preview."""
    from fastapi.responses import StreamingResponse
    import fitz  # PyMuPDF

    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or not label.product or label.product.user_id != user.id:
        return JSONResponse({"detail": "Label not found"}, status_code=404)

    file_path = label.file_path
    if not file_path or not Path(file_path).exists():
        return JSONResponse({"detail": "File not found"}, status_code=404)

    try:
        doc = fitz.open(file_path)
        if page_num < 0 or page_num >= len(doc):
            doc.close()
            return JSONResponse({"detail": "Page not found"}, status_code=404)

        page = doc[page_num]
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        doc.close()

        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        return JSONResponse({"detail": f"Error rendering PDF: {e}"}, status_code=500)


@router.post("/labels/{label_id}/update-fields")
async def update_extraction_fields(label_id: int, request: Request, db: Session = Depends(get_db)):
    """Save edited extraction fields and re-run compliance checks."""
    user = require_user(request, db)
    if not user:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or not label.product or label.product.user_id != user.id:
        return JSONResponse({"detail": "Label not found"}, status_code=404)

    try:
        updated_data = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)

    # Merge with existing extraction (preserve internal fields like _extraction_warnings)
    existing = label.extraction_json or {}
    existing.update(updated_data)
    label.extraction_json = existing
    db.commit()

    # Delete old compliance checks for this label version
    db.query(ComplianceCheck).filter(ComplianceCheck.label_version_id == label_id).delete()
    db.commit()

    # Re-run compliance engine
    checks = run_compliance_check(label, db)
    score = calculate_compliance_score(checks)

    # Also invalidate any existing compliance report so it gets regenerated
    existing_report = db.query(ComplianceReport).filter(
        ComplianceReport.label_version_id == label_id
    ).first()
    if existing_report:
        existing_report.score = score
        # Update verdict
        if score >= 90:
            existing_report.verdict = "COMPLIANT"
        elif score >= 60:
            existing_report.verdict = "PARTIAL"
        else:
            existing_report.verdict = "NON_COMPLIANT"
        db.commit()

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "label_fields_edited", "label", label_id,
                   detail=f"Edited extraction fields for {label.product.name}, new score: {score}%")
    except Exception:
        pass

    return JSONResponse({"success": True, "score": score})
