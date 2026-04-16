import datetime
import io
import os
import threading
import time as _time_mod
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Product, LabelVersion, ComplianceCheck, Alert,
    AlertType, AlertStatus, CheckResult, Severity, ComplianceReport,
)
from app.routes.auth import get_current_user_from_cookie
from app.services.ocr_service import extract_text_from_file
from app.services.extraction_service import (
    extract_label_data, extract_label_data_from_image, _cross_check_with_ocr,
)
from app.services.compliance_engine import (
    run_compliance_check, calculate_compliance_score,
    calculate_critical_score, get_violation_summary,
)
from app.config import get_settings

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".pdf", ".webp"}

SCAN_TIMEOUT_SECS   = 360   # 6 min: hard ceiling for active scan (matches MAX_POLLS×POLL_MS)
SCAN_STALE_SECS     = 900   # 15 min: prune completed entries from _SCAN_JOBS

# In-memory job tracker — same pattern as _EXTRACTION_JOBS in admin_llm.py.
# --workers 1 ensures this dict is shared by all requests.
_SCAN_JOBS: dict[int, dict] = {}


def _prune_scan_jobs() -> None:
    """Remove completed job entries older than SCAN_STALE_SECS to prevent unbounded growth."""
    cutoff = _time_mod.time() - SCAN_STALE_SECS
    stale = [k for k, v in _SCAN_JOBS.items() if v.get("done") and v.get("started", 0) < cutoff]
    for k in stale:
        _SCAN_JOBS.pop(k, None)


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

    # Validate MIME type via file magic bytes (shared utility)
    from app.utils.file_validation import validate_file_magic
    detected_ext = validate_file_magic(content)
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
        file_data=content,
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
    """Background task: extract label data → compliance check → alerts.

    Uses _SCAN_JOBS dict for real-time status tracking (same pattern as
    _EXTRACTION_JOBS in admin_llm.py). The status endpoint reads this
    dict directly — no DB polling race conditions.

    Every step is individually wrapped in try/except. The function
    ALWAYS reaches the end. job["done"] is ALWAYS set to True.
    """
    from app.database import SessionLocal

    _prune_scan_jobs()
    t0 = _time_mod.time()
    job = {
        "started": t0,
        "done": False,
        "ready": False,
        "step": "starting",
        "error": None,
    }
    _SCAN_JOBS[label_version_id] = job
    print(f"[scan] START id={label_version_id}", flush=True)

    db = SessionLocal()
    try:
        # ── Load label + product ──────────────────────────────────────────
        job["step"] = "loading"
        label = db.query(LabelVersion).filter(
            LabelVersion.id == label_version_id
        ).first()
        if not label:
            job["error"] = "Label not found"
            print(f"[scan] ERROR: label {label_version_id} not in DB", flush=True)
            return
        product = label.product
        if not product:
            job["error"] = "Product not found"
            print(f"[scan] ERROR: no product for label {label_version_id}", flush=True)
            return

        file_path = label.file_path
        print(f"[scan] file={file_path} product={product.name}", flush=True)

        # ── Check file exists on disk ─────────────────────────────────────
        if not Path(file_path).exists():
            job["error"] = f"File not found: {file_path}"
            print(f"[scan] ERROR: file missing on disk: {file_path}", flush=True)
            label.extraction_json = {}
            label.extraction_source = "error"
            db.commit()
            # Still run compliance so page loads (all rules fail = informative)
            job["step"] = "compliance"
            run_compliance_check(label, db)
            job["ready"] = True
            return

        # ── Check for cached extraction ───────────────────────────────────
        if (label.extraction_json
                and label.extraction_confidence
                and label.extraction_confidence >= 0.85):
            job["step"] = "cached"
            print(f"[scan] Using cached extraction conf={label.extraction_confidence:.2f}", flush=True)
        else:
            # Ensure API key is available
            cfg = get_settings()
            if cfg.anthropic_api_key:
                os.environ["ANTHROPIC_API_KEY"] = cfg.anthropic_api_key

            extraction = None
            confidence = 0.0
            source = "none"
            inp = out = 0

            # ── STEP 1: AI Vision ─────────────────────────────────────────
            job["step"] = "ai_vision"
            print("[scan] Step 1: AI Vision...", flush=True)
            try:
                extraction, confidence, source, inp, out = \
                    extract_label_data_from_image(file_path)
                print(f"[scan] Vision OK in {_time_mod.time()-t0:.1f}s "
                      f"source={source} conf={confidence:.2f}", flush=True)
            except Exception as e:
                print(f"[scan] Vision FAILED: {e}", flush=True)
                extraction = None

            # ── STEP 2: OCR + Text fallback ───────────────────────────────
            if not extraction or confidence < 0.40:
                job["step"] = "ocr_fallback"
                print("[scan] Step 2: OCR fallback...", flush=True)
                raw_text = ""
                try:
                    raw_text, _ = extract_text_from_file(file_path)
                    print(f"[scan] OCR: {len(raw_text)} chars", flush=True)
                except Exception as e:
                    print(f"[scan] OCR failed: {e}", flush=True)

                if raw_text:
                    try:
                        extraction, confidence, source, inp, out = \
                            extract_label_data(raw_text)
                        if extraction:
                            extraction = _cross_check_with_ocr(extraction, raw_text)
                        print(f"[scan] Text: source={source} conf={confidence:.2f}", flush=True)
                    except Exception as e:
                        print(f"[scan] Text extraction failed: {e}", flush=True)

            # ── Save extraction ───────────────────────────────────────────
            job["step"] = "saving"
            if not extraction:
                extraction = {}
            label.extraction_json = extraction
            label.extraction_confidence = confidence
            label.extraction_source = source
            label.tokens_input = inp
            label.tokens_output = out
            db.commit()
            print(f"[scan] Extraction saved in {_time_mod.time()-t0:.1f}s", flush=True)

        # ── STEP 3: Compliance check ──────────────────────────────────────
        job["step"] = "compliance"
        print("[scan] Step 3: Compliance...", flush=True)
        try:
            checks = run_compliance_check(label, db)
            print(f"[scan] Compliance: {len(checks)} checks", flush=True)
        except Exception as e:
            print(f"[scan] Compliance FAILED: {e}\n{traceback.format_exc()}", flush=True)
            # Force-create a minimal check so status shows ready
            try:
                from app.models import ComplianceRule
                label.extraction_json = label.extraction_json or {}
                db.commit()
                checks = []
            except Exception:
                pass

        # ── Mark ready BEFORE alerts/KB (those are non-critical) ──────────
        job["ready"] = True
        print(f"[scan] READY in {_time_mod.time()-t0:.1f}s", flush=True)

        # ── Alerts (non-critical) ─────────────────────────────────────────
        try:
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

            crit = [v for v in violations if v["severity"] == "CRITICAL"]
            high = [v for v in violations if v["severity"] == "HIGH"]
            if crit or high:
                score = calculate_compliance_score(checks)
                alert = Alert(
                    product_id=label.product_id,
                    label_version_id=label.id,
                    alert_type=AlertType.LABEL_VIOLATION,
                    severity=Severity.CRITICAL if crit else Severity.HIGH,
                    title=f"Label compliance issues — {len(violations)} violation(s)",
                    message=f"Score: {score}%. {len(crit)} critical, {len(high)} high.",
                    rule_violations=violations,
                    status=AlertStatus.UNREAD,
                )
                db.add(alert)
                db.commit()

                try:
                    from app.services.notification import send_alert_email
                    from app.models import User
                    owner = db.query(User).filter(User.id == product.user_id).first()
                    send_alert_email(alert, product, user=owner)
                except Exception:
                    pass
        except Exception as e:
            print(f"[scan] Alert creation failed (non-critical): {e}", flush=True)

        # ── KB update (daemon thread — non-critical) ──────────────────────
        try:
            _pid = label.product_id
            def _kb():
                _db = SessionLocal()
                try:
                    from app.services.llm_service import seed_products_kb, invalidate_cache
                    seed_products_kb(_db, force_update_product_id=_pid)
                    invalidate_cache("products")
                except Exception:
                    pass
                try:
                    from app.routes.products import _feed_product_to_llm
                    _feed_product_to_llm(_pid, _db)
                except Exception:
                    pass
                _db.close()
            threading.Thread(target=_kb, daemon=True).start()
        except Exception:
            pass

    except Exception as e:
        print(f"[scan] FATAL id={label_version_id}: {e}\n{traceback.format_exc()}", flush=True)
        job["error"] = str(e)[:200]
        # Last resort: try to make the page loadable
        try:
            lv = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
            if lv:
                if lv.extraction_json is None:
                    lv.extraction_json = {}
                    lv.extraction_source = "error"
                db.commit()
                run_compliance_check(lv, db)
                job["ready"] = True
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        job["done"] = True
        elapsed = _time_mod.time() - t0
        print(f"[scan] DONE id={label_version_id} elapsed={elapsed:.1f}s "
              f"ready={job['ready']} error={job.get('error')}", flush=True)
        try:
            db.close()
        except Exception:
            pass


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

    # Clear old compliance checks so they don't linger during re-scan
    db.query(ComplianceCheck).filter(
        ComplianceCheck.label_version_id == label.id
    ).delete()
    db.commit()

    if force_extract or not label.extraction_json or (label.extraction_confidence or 0) < 0.85:
        # Clear extraction to trigger fresh Vision/OCR extraction
        label.extraction_json = None
        label.extraction_confidence = None
        db.commit()

    background_tasks.add_task(_process_label, label.id)
    return RedirectResponse(url=f"/labels/{label.id}?processing=1", status_code=302)


@router.get("/labels/{label_id}/status")
async def label_status(label_id: int, request: Request, db: Session = Depends(get_db)):
    """JSON polling endpoint — returns {ready, failed, step} for the progress bar.

    Reads _SCAN_JOBS dict first (authoritative while scan is running).
    Falls back to DB check for page refreshes after scan completed.
    """
    user = require_user(request, db)
    if not user:
        return JSONResponse({"ready": False, "failed": False, "step": ""})

    # ── Check in-memory job tracker first (authoritative) ────────────
    job = _SCAN_JOBS.get(label_id)
    if job is not None:
        if job["ready"]:
            return JSONResponse({"ready": True, "failed": False, "step": "done"})
        if job["done"] and not job["ready"]:
            # Finished but never became ready → something failed
            return JSONResponse({"ready": False, "failed": True, "step": job.get("step", "error")})
        # Still running — check for timeout
        age = _time_mod.time() - job["started"]
        if age > SCAN_TIMEOUT_SECS:
            return JSONResponse({"ready": False, "failed": True, "step": "timeout"})
        return JSONResponse({"ready": False, "failed": False, "step": job.get("step", "")})

    # ── No in-memory job → check DB (page refresh after completion) ──
    row = (
        db.query(LabelVersion, Product)
        .join(Product, Product.id == LabelVersion.product_id)
        .filter(LabelVersion.id == label_id, Product.user_id == user.id)
        .first()
    )
    if not row:
        return JSONResponse({"ready": False, "failed": True, "step": ""})

    label, _ = row
    has_checks = db.query(ComplianceCheck.id).filter(
        ComplianceCheck.label_version_id == label_id
    ).first() is not None

    extraction_done = label.extraction_json is not None

    # Ready if both extraction and checks exist
    ready = extraction_done and has_checks

    # ── Edge case: extraction completed but compliance check failed/missing ──
    # If extraction_json is set AND it's been >60 s since upload, treat as ready
    # so the report page loads (showing whatever checks exist, even 0).
    if not ready and extraction_done and label.uploaded_at:
        age_secs = (datetime.datetime.utcnow() - label.uploaded_at).total_seconds()
        if age_secs > 60:
            ready = True

    if ready:
        return JSONResponse({"ready": True, "failed": False, "step": "done"})

    # Not ready and no in-memory job → scan may have been lost (server restart)
    failed = False
    if label.uploaded_at:
        age_secs = (datetime.datetime.utcnow() - label.uploaded_at).total_seconds()
        if age_secs > SCAN_STALE_SECS:
            failed = True

    return JSONResponse({"ready": ready, "failed": failed, "step": ""})


@router.get("/labels/{label_id}")
async def label_report(label_id: int, request: Request, processing: int = 0, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    from sqlalchemy.orm import joinedload
    label = (
        db.query(LabelVersion)
        .options(joinedload(LabelVersion.checks).joinedload(ComplianceCheck.rule))
        .filter(LabelVersion.id == label_id)
        .first()
    )
    if not label or not label.product or label.product.user_id != user.id:
        return RedirectResponse(url="/products")

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
        "processing": bool(processing) and not label.checks,
        "CheckResult": CheckResult,
        "existing_report": existing_report,
    })


@router.get("/labels/{label_id}/image")
async def label_image(label_id: int, request: Request = None, db: Session = Depends(get_db)):
    """Serve the label image/first PDF page. DB bytes first, disk fallback."""
    from fastapi.responses import StreamingResponse
    import fitz  # PyMuPDF

    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or not label.product or label.product.user_id != user.id:
        return JSONResponse({"detail": "Label not found"}, status_code=404)

    # Resolve bytes: prefer DB, fall back to disk
    raw: bytes | None = label.file_data
    if not raw and label.file_path and Path(label.file_path).exists():
        raw = Path(label.file_path).read_bytes()

    if not raw:
        return JSONResponse({"detail": "File not available"}, status_code=404)

    try:
        if label.file_type == "pdf":
            doc = fitz.open(stream=raw, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            doc.close()
            return StreamingResponse(
                io.BytesIO(img_bytes),
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600"},
            )
        else:
            # image — detect mime type from magic bytes
            mime = "image/jpeg"
            if raw[:4] == b"\x89PNG":
                mime = "image/png"
            elif raw[:4] == b"GIF8":
                mime = "image/gif"
            elif raw[:4] == b"RIFF":
                mime = "image/webp"
            return StreamingResponse(
                io.BytesIO(raw),
                media_type=mime,
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except Exception as e:
        return JSONResponse({"detail": f"Error serving file: {e}"}, status_code=500)


@router.get("/labels/{label_id}/preview-page/{page_num}")
async def label_preview_page(label_id: int, page_num: int = 0, request: Request = None, db: Session = Depends(get_db)):
    """Serve a PDF page as a PNG image for preview. DB bytes first, disk fallback."""
    from fastapi.responses import StreamingResponse
    import fitz  # PyMuPDF

    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label or not label.product or label.product.user_id != user.id:
        return JSONResponse({"detail": "Label not found"}, status_code=404)

    # Resolve bytes: prefer DB, fall back to disk
    raw: bytes | None = label.file_data
    if not raw and label.file_path and Path(label.file_path).exists():
        raw = Path(label.file_path).read_bytes()

    if not raw:
        return JSONResponse({"detail": "File not found"}, status_code=404)

    try:
        doc = fitz.open(stream=raw, filetype="pdf")
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
