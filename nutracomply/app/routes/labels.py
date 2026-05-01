import datetime
import io
import os
import tempfile
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
    Product, LabelVersion, ComplianceCheck, Alert, CheckerSession,
    AlertType, AlertStatus, CheckResult, Severity, ComplianceReport,
)
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import can_upload_labels, get_account_contact_user, get_account_id
from app.services.upload_service import persist_upload_bytes, validate_upload_content
from app.services.ocr_service import extract_text_from_file
from app.services.extraction_service import (
    CRITICAL_FIELDS, IMPORTANT_FIELDS, _validate_extraction,
    extract_label_data, extract_label_data_from_image,
)
from app.services.local_extraction_service import extract_locally
from app.services.compliance_engine import (
    run_compliance_check, calculate_compliance_score,
    calculate_critical_score, get_violation_summary,
)
from app.services.activity_service import log_action
from app.config import get_settings
from app.services.scan_eta_service import format_eta_window
from app.services.verdict_service import build_verdict, summarize_checks

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".pdf", ".webp"}
PROCESSING_QUEUED = "queued"
PROCESSING_PROCESSING = "processing"
PROCESSING_READY = "ready"
PROCESSING_FAILED = "failed"

SCAN_TIMEOUT_SECS   = 360   # 6 min: hard ceiling for active scan (matches MAX_POLLS×POLL_MS)
SCAN_STALE_SECS     = 900   # 15 min: prune completed entries from _SCAN_JOBS

# In-memory job tracker — same pattern as _EXTRACTION_JOBS in admin_llm.py.
# --workers 1 ensures this dict is shared by all requests.
_SCAN_JOBS: dict[int, dict] = {}
_UNSET = object()


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


def _owned_product_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(Product)
    if account_id:
        query = query.filter(Product.account_id == account_id)
    else:
        query = query.filter(Product.user_id == user.id)
    return query


def _owned_label_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(LabelVersion).join(Product, LabelVersion.product_id == Product.id)
    if account_id:
        query = query.filter(Product.account_id == account_id)
    else:
        query = query.filter(Product.user_id == user.id)
    return query


def _field_filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, dict)):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _critical_field_count(extraction: dict | None) -> int:
    extraction = extraction or {}
    return sum(1 for field in CRITICAL_FIELDS if _field_filled(extraction.get(field)))


def _important_field_count(extraction: dict | None) -> int:
    extraction = extraction or {}
    return sum(1 for field in IMPORTANT_FIELDS if _field_filled(extraction.get(field)))


def _extraction_completeness(extraction: dict | None) -> float:
    extraction = extraction or {}
    critical_total = len(CRITICAL_FIELDS) or 1
    important_total = len(IMPORTANT_FIELDS) or 1
    critical_ratio = _critical_field_count(extraction) / critical_total
    important_ratio = _important_field_count(extraction) / important_total
    return round((critical_ratio * 0.7) + (important_ratio * 0.3), 3)


def _needs_review(confidence: float | None, warnings: list[str] | None) -> bool:
    confidence = confidence or 0.0
    return confidence < settings.label_scan_review_confidence or bool(warnings)


def _local_fast_path_ok(extraction: dict | None, confidence: float | None) -> bool:
    confidence = confidence or 0.0
    return (
        bool(extraction)
        and confidence >= settings.local_extraction_min_confidence
        and _extraction_completeness(extraction) >= settings.label_scan_local_min_completeness
        and _critical_field_count(extraction) >= settings.label_scan_local_min_critical_fields
    )


def _candidate_quality(extraction: dict | None, confidence: float | None, source: str) -> float:
    confidence = confidence or 0.0
    completeness = _extraction_completeness(extraction)
    source_bonus = 0.04 if source in {"claude", "gemini"} else 0.0
    source_penalty = -0.04 if source == "fallback" else 0.0
    return round((completeness * 0.65) + (confidence * 0.35) + source_bonus + source_penalty, 3)


def _status_payload(label: LabelVersion | None, job: dict | None = None) -> dict:
    if not label and not job:
        return {
            "status": PROCESSING_FAILED,
            "step": "",
            "ready": False,
            "failed": True,
            "error": "Label not found",
            "retry_allowed": False,
            "needs_review": False,
        }

    status = label.processing_status if label else None
    step = label.processing_step if label else ""
    error = label.processing_error if label else None
    needs_review = bool(label.needs_review) if label else False

    if job:
        status = job.get("status", status)
        step = job.get("step", step)
        error = job.get("error", error)
        needs_review = job.get("needs_review", needs_review)

    retry_allowed = _scan_retry_allowed(label)
    ready = status == PROCESSING_READY
    failed = status == PROCESSING_FAILED
    return {
        "status": status or "",
        "step": step or "",
        "ready": ready,
        "failed": failed,
        "error": error,
        "retry_allowed": retry_allowed,
        "needs_review": bool(needs_review),
    }


def _has_file_source(label: LabelVersion | None) -> bool:
    if not label:
        return False
    return bool(label.file_data) or bool(label.file_path and Path(label.file_path).exists())


def _scan_source_available(label: LabelVersion | None) -> bool:
    if not label:
        return False
    return _has_file_source(label) or bool((label.ocr_raw_text or "").strip())


def _scan_retry_allowed(label: LabelVersion | None) -> bool:
    if not label:
        return False
    if not _scan_source_available(label):
        return False
    if label.processing_status == PROCESSING_FAILED:
        return True
    if label.processing_status in {PROCESSING_QUEUED, PROCESSING_PROCESSING} and label.processing_started_at:
        age_secs = (datetime.datetime.utcnow() - label.processing_started_at).total_seconds()
        return age_secs > SCAN_STALE_SECS
    return False


def _update_processing_state(
    label: LabelVersion,
    db: Session,
    *,
    status=_UNSET,
    step=_UNSET,
    error=_UNSET,
    started_at=_UNSET,
    finished_at=_UNSET,
    needs_review=_UNSET,
) -> None:
    if status is not _UNSET:
        label.processing_status = status
    if step is not _UNSET:
        label.processing_step = step
    if error is not _UNSET:
        label.processing_error = error
    if started_at is not _UNSET:
        label.processing_started_at = started_at
    if finished_at is not _UNSET:
        label.processing_finished_at = finished_at
    if needs_review is not _UNSET:
        label.needs_review = needs_review
    db.commit()


def _set_job_state(job: dict, *, status=None, step=None, error=None, needs_review=None, done=None, ready=None) -> None:
    if status is not None:
        job["status"] = status
    if step is not None:
        job["step"] = step
    if error is not None:
        job["error"] = error
    if needs_review is not None:
        job["needs_review"] = needs_review
    if done is not None:
        job["done"] = done
    if ready is not None:
        job["ready"] = ready


def _set_processing_step(label: LabelVersion, db: Session, job: dict, step: str) -> None:
    _set_job_state(job, status=PROCESSING_PROCESSING, step=step)
    _update_processing_state(label, db, status=PROCESSING_PROCESSING, step=step, error=None)


def _prime_label_processing(label: LabelVersion, db: Session) -> None:
    _SCAN_JOBS.pop(label.id, None)
    _update_processing_state(
        label,
        db,
        status=PROCESSING_QUEUED,
        step="queued",
        error=None,
        started_at=None,
        finished_at=None,
        needs_review=False,
    )


def _prepare_scan_file(label: LabelVersion) -> tuple[str, list[str]]:
    """Return the fastest available local file path for scan work plus temp paths to delete."""
    cleanup_paths: list[str] = []
    original_path = label.file_path or ""
    working_path = original_path

    if not original_path or not Path(original_path).exists():
        if not label.file_data:
            return original_path, cleanup_paths
        suffix = Path(original_path or label.file_name or "").suffix.lower()
        if not suffix:
            suffix = ".pdf" if label.file_type == "pdf" else ".png"
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp.write(label.file_data)
        temp.flush()
        temp.close()
        working_path = temp.name
        cleanup_paths.append(temp.name)

    if label.file_type == "pdf":
        return working_path, cleanup_paths

    try:
        from PIL import Image

        image = Image.open(working_path)
        max_edge = max(image.size)
        file_size = len(label.file_data or b"") or (Path(working_path).stat().st_size if Path(working_path).exists() else 0)
        if max_edge <= 1800 and file_size <= 2_500_000:
            image.close()
            return working_path, cleanup_paths

        image = image.convert("RGB")
        if max_edge > 1800:
            ratio = 1800 / max_edge
            image = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.LANCZOS)

        normalized = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        image.save(normalized, format="JPEG", quality=82, optimize=True)
        normalized.flush()
        normalized.close()
        image.close()
        cleanup_paths.append(normalized.name)
        return normalized.name, cleanup_paths
    except Exception:
        return working_path, cleanup_paths


@router.get("/products/{product_id}/upload")
async def upload_page(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_upload_labels(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    product = _owned_product_query(db, user).filter(Product.id == product_id).first()
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
    from urllib.parse import quote

    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_upload_labels(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

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
            return RedirectResponse(url=f"/products/{product_id}?msg={quote(quota_msg)}&type=error", status_code=302)
    except Exception:
        pass

    product = _owned_product_query(db, user).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse(url="/products")
    try:
        content = await file.read()
        suffix = validate_upload_content(file.filename or "", content)
        file_path = persist_upload_bytes(settings.upload_dir, str(product_id), suffix, content)
    except ValueError as exc:
        return templates.TemplateResponse("label_upload.html", {
            "request": request,
            "user": user,
            "product": product,
            "error": str(exc),
        })

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
        processing_status=PROCESSING_QUEUED,
        processing_step="queued",
        needs_review=False,
        is_current=True,
        file_data=content,
    )
    db.add(label_version)
    db.commit()
    db.refresh(label_version)
    _prime_label_processing(label_version, db)

    log_action(
        user.id,
        "label_uploaded",
        "label",
        label_version.id,
        detail=f"Uploaded label for {product.name}",
        request=request,
        context={"product_id": product.id, "file_name": file.filename},
    )

    # Run OCR + extraction + compliance check in background
    background_tasks.add_task(_process_label_balanced, label_version.id)

    eta_text = format_eta_window([label_version.file_type or "image"])
    msg = (
        f"Queued background analysis for {product.name}. Go to Products - "
        f"we'll notify you when the label is ready. Estimated {eta_text}."
    )
    return RedirectResponse(url=f"/products?msg={quote(msg)}&type=success", status_code=302)


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
                    account_id=product.account_id,
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
                    owner = get_account_contact_user(db, product.account_id) or product.owner
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


def _process_label_balanced(label_version_id: int):
    """DB-backed label scan worker with a balanced local-first extraction path."""
    from app.database import SessionLocal

    _prune_scan_jobs()
    t0 = _time_mod.time()
    job = {
        "started": t0,
        "done": False,
        "ready": False,
        "status": PROCESSING_QUEUED,
        "step": "starting",
        "error": None,
        "needs_review": False,
    }
    _SCAN_JOBS[label_version_id] = job
    print(f"[scan-v2] START id={label_version_id}", flush=True)

    db = SessionLocal()
    cleanup_paths: list[str] = []
    try:
        _set_job_state(job, status=PROCESSING_PROCESSING, step="loading")
        label = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
        if not label:
            _set_job_state(job, status=PROCESSING_FAILED, error="Label not found")
            print(f"[scan-v2] ERROR: label {label_version_id} not in DB", flush=True)
            return

        _update_processing_state(
            label,
            db,
            status=PROCESSING_PROCESSING,
            step="loading",
            error=None,
            started_at=datetime.datetime.utcnow(),
            finished_at=None,
            needs_review=False,
        )

        product = label.product
        if not product:
            _set_job_state(job, status=PROCESSING_FAILED, error="Product not found")
            _update_processing_state(
                label,
                db,
                status=PROCESSING_FAILED,
                step="loading",
                error="Product not found",
                finished_at=datetime.datetime.utcnow(),
            )
            print(f"[scan-v2] ERROR: no product for label {label_version_id}", flush=True)
            return

        source_path = label.file_path or ""
        raw_text = label.ocr_raw_text or ""
        has_file_source = _has_file_source(label)
        if not has_file_source and not raw_text.strip():
            err = f"Label source is unavailable: {source_path or label.file_name or 'unknown file'}"
            _set_job_state(job, status=PROCESSING_FAILED, error=err)
            _update_processing_state(
                label,
                db,
                status=PROCESSING_FAILED,
                step="loading",
                error=err,
                finished_at=datetime.datetime.utcnow(),
            )
            print(f"[scan-v2] ERROR: {err}", flush=True)
            return

        cfg = get_settings()
        if cfg.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = cfg.anthropic_api_key

        extraction = None
        confidence = 0.0
        source = "none"
        inp = 0
        out = 0
        warnings: list[str] = []
        best_candidate = None
        stage_timings: dict[str, float] = {}
        working_path = ""
        cleanup_paths: list[str] = []
        if has_file_source:
            stage_start = _time_mod.time()
            working_path, cleanup_paths = _prepare_scan_file(label)
            stage_timings["normalize_sec"] = round(_time_mod.time() - stage_start, 2)
            if not working_path or not Path(working_path).exists():
                raise FileNotFoundError(source_path or "Label file is unavailable")
        else:
            stage_timings["normalize_sec"] = 0.0
            print("[scan-v2] Reusing stored OCR text without original file", flush=True)

        def remember_candidate(result, result_confidence, result_source, token_in=0, token_out=0, result_text=None):
            nonlocal best_candidate
            if not result:
                return
            candidate_data = dict(result)
            candidate_warnings = _validate_extraction(candidate_data)
            if candidate_warnings:
                candidate_data["_extraction_warnings"] = candidate_warnings
            candidate = {
                "extraction": candidate_data,
                "confidence": result_confidence or 0.0,
                "source": result_source,
                "inp": token_in,
                "out": token_out,
                "raw_text": result_text if result_text is not None else raw_text,
                "warnings": candidate_warnings,
                "completeness": _extraction_completeness(candidate_data),
                "quality": _candidate_quality(candidate_data, result_confidence, result_source),
            }
            if best_candidate is None or candidate["quality"] > best_candidate["quality"]:
                best_candidate = candidate

        if label.extraction_json and (label.extraction_confidence or 0) >= 0.85:
            extraction = dict(label.extraction_json)
            confidence = label.extraction_confidence or 0.0
            source = label.extraction_source or "cached"
            inp = label.tokens_input or 0
            out = label.tokens_output or 0
            warnings = list(extraction.get("_extraction_warnings", []))
            remember_candidate(extraction, confidence, source, inp, out, raw_text)
            print(f"[scan-v2] Using cached extraction conf={confidence:.2f}", flush=True)
        else:
            if has_file_source:
                _set_processing_step(label, db, job, "text_fastpath")
                stage_start = _time_mod.time()
                prior_raw_text = raw_text
                try:
                    raw_text, _ocr_confidence = extract_text_from_file(
                        working_path,
                        allow_ocr_fallback=(label.file_type != "pdf"),
                    )
                    if raw_text:
                        label.ocr_raw_text = raw_text
                        db.commit()
                        print(f"[scan-v2] Text fast path yielded {len(raw_text)} chars", flush=True)
                    else:
                        raw_text = prior_raw_text
                        if raw_text:
                            print("[scan-v2] Text fast path was empty; reusing stored OCR text", flush=True)
                except Exception as exc:
                    raw_text = label.ocr_raw_text or ""
                    print(f"[scan-v2] Text fast path failed: {exc}", flush=True)
                stage_timings["text_fastpath_sec"] = round(_time_mod.time() - stage_start, 2)
            else:
                stage_timings["text_fastpath_sec"] = 0.0

            if raw_text and settings.local_extraction_enabled:
                _set_processing_step(label, db, job, "local_extraction")
                stage_start = _time_mod.time()
                try:
                    local_result, local_confidence = extract_locally(raw_text, db)
                    remember_candidate(local_result, local_confidence, "local", result_text=raw_text)
                    print(
                        f"[scan-v2] Local extraction conf={local_confidence:.2f} "
                        f"completeness={_extraction_completeness(local_result):.2f}",
                        flush=True,
                    )
                    if _local_fast_path_ok(local_result, local_confidence):
                        extraction = dict(local_result)
                        confidence = local_confidence
                        source = "local"
                        warnings = _validate_extraction(extraction)
                        if warnings:
                            extraction["_extraction_warnings"] = warnings
                        print(f"[scan-v2] Local fast path accepted in {_time_mod.time()-t0:.1f}s", flush=True)
                except Exception as exc:
                    print(f"[scan-v2] Local extraction failed: {exc}", flush=True)
                stage_timings["local_extraction_sec"] = round(_time_mod.time() - stage_start, 2)

            if extraction is None and label.file_type == "pdf" and raw_text and len(raw_text.strip()) >= 120:
                _set_processing_step(label, db, job, "text_ai")
                stage_start = _time_mod.time()
                try:
                    text_result, text_confidence, text_source, inp, out = extract_label_data(raw_text)
                    remember_candidate(text_result, text_confidence, text_source, inp, out, raw_text)
                    if best_candidate and best_candidate["completeness"] >= settings.label_scan_local_min_completeness:
                        extraction = best_candidate["extraction"]
                        confidence = best_candidate["confidence"]
                        source = best_candidate["source"]
                        inp = best_candidate["inp"]
                        out = best_candidate["out"]
                        warnings = best_candidate["warnings"]
                        print(
                            f"[scan-v2] PDF text path accepted source={source} conf={confidence:.2f}",
                            flush=True,
                        )
                except Exception as exc:
                    print(f"[scan-v2] Text AI extraction failed: {exc}", flush=True)
                stage_timings["text_ai_sec"] = round(_time_mod.time() - stage_start, 2)

            if extraction is None and has_file_source:
                _set_processing_step(label, db, job, "ai_vision")
                stage_start = _time_mod.time()
                try:
                    vision_result, vision_confidence, vision_source, inp, out = extract_label_data_from_image(working_path)
                    remember_candidate(vision_result, vision_confidence, vision_source, inp, out, raw_text)
                    if best_candidate and (
                        best_candidate["completeness"] >= settings.label_scan_local_min_completeness
                        or best_candidate["confidence"] >= settings.label_scan_review_confidence
                    ):
                        extraction = best_candidate["extraction"]
                        confidence = best_candidate["confidence"]
                        source = best_candidate["source"]
                        inp = best_candidate["inp"]
                        out = best_candidate["out"]
                        warnings = best_candidate["warnings"]
                    print(
                        f"[scan-v2] Vision candidate source={vision_source} conf={vision_confidence:.2f}",
                        flush=True,
                    )
                except Exception as exc:
                    print(f"[scan-v2] Vision failed: {exc}", flush=True)
                stage_timings["vision_sec"] = round(_time_mod.time() - stage_start, 2)

            if extraction is None:
                if not raw_text and has_file_source:
                    _set_processing_step(label, db, job, "ocr_fallback")
                    stage_start = _time_mod.time()
                    try:
                        raw_text, _ocr_confidence = extract_text_from_file(working_path)
                        label.ocr_raw_text = raw_text or label.ocr_raw_text
                        db.commit()
                    except Exception as exc:
                        print(f"[scan-v2] OCR fallback failed: {exc}", flush=True)
                    stage_timings["ocr_fallback_sec"] = round(_time_mod.time() - stage_start, 2)

                if raw_text:
                    _set_processing_step(label, db, job, "text_fallback")
                    stage_start = _time_mod.time()
                    try:
                        text_result, text_confidence, text_source, inp, out = extract_label_data(raw_text)
                        remember_candidate(text_result, text_confidence, text_source, inp, out, raw_text)
                    except Exception as exc:
                        print(f"[scan-v2] Text fallback failed: {exc}", flush=True)
                    stage_timings["text_fallback_sec"] = round(_time_mod.time() - stage_start, 2)

            if extraction is None and best_candidate:
                extraction = best_candidate["extraction"]
                confidence = best_candidate["confidence"]
                source = best_candidate["source"]
                inp = best_candidate["inp"]
                out = best_candidate["out"]
                raw_text = best_candidate["raw_text"] or raw_text
                warnings = best_candidate["warnings"]

            if extraction is None:
                extraction = {}
                confidence = 0.0
                source = "none"
                warnings = []

            _set_processing_step(label, db, job, "saving")
            label.ocr_raw_text = raw_text or label.ocr_raw_text
            label.extraction_json = extraction
            label.extraction_confidence = confidence
            label.extraction_source = source
            label.tokens_input = inp
            label.tokens_output = out
            label.needs_review = _needs_review(confidence, warnings)
            db.commit()
            _set_job_state(job, needs_review=label.needs_review)
            print(
                f"[scan-v2] Extraction saved source={source} conf={confidence:.2f} "
                f"completeness={_extraction_completeness(extraction):.2f} timings={stage_timings}",
                flush=True,
            )

        _set_processing_step(label, db, job, "compliance")
        stage_start = _time_mod.time()
        checks = run_compliance_check(label, db)
        stage_timings["compliance_sec"] = round(_time_mod.time() - stage_start, 2)
        print(f"[scan-v2] Compliance: {len(checks)} checks", flush=True)

        try:
            if product.is_temporary:
                from app.services.report_service import get_or_create_report

                checker_session = (
                    db.query(CheckerSession)
                    .filter(CheckerSession.label_version_id == label.id)
                    .first()
                )
                report = get_or_create_report(
                    db,
                    product.user_id,
                    product.id,
                    label.id,
                    checker_session_id=checker_session.id if checker_session else None,
                )
                print(f"[scan-v2] Report ready id={report.id}", flush=True)
        except Exception as exc:
            print(f"[scan-v2] Report generation skipped: {exc}", flush=True)

        _set_job_state(job, status=PROCESSING_READY, ready=True, needs_review=label.needs_review)
        _update_processing_state(
            label,
            db,
            status=PROCESSING_READY,
            step="done",
            error=None,
            finished_at=datetime.datetime.utcnow(),
            needs_review=label.needs_review,
        )
        stage_timings["total_scan_sec"] = round(_time_mod.time() - t0, 2)
        print(
            f"[scan-v2] READY in {_time_mod.time()-t0:.1f}s "
            f"needs_review={label.needs_review} timings={stage_timings}",
            flush=True,
        )
        log_action(
            product.user_id,
            "label_scan_completed",
            "label",
            label.id,
            detail=(
                f"Completed scan for {product.name} "
                f"({source or 'unknown source'}, {confidence:.0%} confidence)"
            ),
            account_id=product.account_id,
            context={
                "product_id": product.id,
                "product_name": product.name,
                "needs_review": label.needs_review,
                "extraction_source": source,
                "confidence": round(confidence or 0.0, 3),
                "timings": stage_timings,
                "status": PROCESSING_READY,
            },
        )
        try:
            from app.services.notify_service import push

            scan_summary = summarize_checks(checks)
            score_value = scan_summary.get("score")
            score_text = f"{score_value}%" if score_value is not None else "No score"
            notification_type = (
                "success"
                if scan_summary.get("verdict") == "COMPLIANT" and not label.needs_review
                else "warning"
                if scan_summary.get("verdict") == "PARTIAL" or label.needs_review
                else "alert"
            )
            push(
                product.user_id,
                f"Label analysis ready — {product.name}",
                f"{scan_summary.get('label') or 'Ready'} · {score_text}. Open the latest scan result.",
                ntype=notification_type,
                link=f"/labels/{label.id}",
            )
        except Exception:
            pass

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
                    account_id=product.account_id,
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
                    owner = get_account_contact_user(db, product.account_id) or product.owner
                    send_alert_email(alert, product, user=owner)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[scan-v2] Alert creation failed (non-critical): {exc}", flush=True)

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

    except Exception as exc:
        print(f"[scan-v2] FATAL id={label_version_id}: {exc}\n{traceback.format_exc()}", flush=True)
        _set_job_state(job, status=PROCESSING_FAILED, error=str(exc)[:200])
        try:
            lv = db.query(LabelVersion).filter(LabelVersion.id == label_version_id).first()
            if lv:
                _update_processing_state(
                    lv,
                    db,
                    status=PROCESSING_FAILED,
                    step=job.get("step", "error"),
                    error=str(exc)[:200],
                    finished_at=datetime.datetime.utcnow(),
                )
                if lv.product:
                    log_action(
                        lv.product.user_id,
                        "label_scan_failed",
                        "label",
                        lv.id,
                        detail=f"Scan failed for {lv.product.name}: {str(exc)[:120]}",
                        account_id=lv.product.account_id,
                        status="failed",
                        context={
                            "product_id": lv.product.id,
                            "product_name": lv.product.name,
                            "step": job.get("step", "error"),
                            "error": str(exc)[:200],
                        },
                    )
                    try:
                        from app.services.notify_service import push

                        push(
                            lv.product.user_id,
                            f"Label analysis failed — {lv.product.name}",
                            "The latest scan did not finish cleanly. Open the label to retry the analysis.",
                            ntype="alert",
                            link=f"/labels/{lv.id}",
                        )
                    except Exception:
                        pass
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        _set_job_state(job, done=True)
        elapsed = _time_mod.time() - t0
        print(
            f"[scan-v2] DONE id={label_version_id} elapsed={elapsed:.1f}s "
            f"ready={job['ready']} status={job.get('status')} error={job.get('error')}",
            flush=True,
        )
        for temp_path in cleanup_paths:
            try:
                if temp_path and Path(temp_path).exists():
                    Path(temp_path).unlink()
            except Exception:
                pass
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
    if not can_upload_labels(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    label = _owned_label_query(db, user).filter(LabelVersion.id == label_id).first()
    if not label or not label.product:
        return RedirectResponse(url="/products")
    if not _scan_source_available(label):
        return RedirectResponse(url=f"/labels/{label_id}?msg=Original+label+content+is+not+available&type=error", status_code=302)

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

    _prime_label_processing(label, db)
    background_tasks.add_task(_process_label_balanced, label.id)
    log_action(
        user.id,
        "label_reanalyzed",
        "label",
        label.id,
        detail=f"Queued re-analysis for {label.product.name}",
        request=request,
        context={"product_id": label.product.id, "force_extract": force_extract},
    )
    return RedirectResponse(url=f"/labels/{label.id}?processing=1", status_code=302)


@router.post("/labels/{label_id}/retry")
async def retry_label_scan(
    label_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_upload_labels(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    label = _owned_label_query(db, user).filter(LabelVersion.id == label_id).first()
    if not label or not label.product:
        return RedirectResponse(url="/products")

    if not _scan_source_available(label):
        return RedirectResponse(url=f"/labels/{label_id}?msg=Original+label+content+is+not+available&type=error", status_code=302)

    db.query(ComplianceCheck).filter(ComplianceCheck.label_version_id == label.id).delete()
    label.processing_error = None
    label.extraction_json = None
    label.extraction_confidence = None
    label.extraction_source = None
    label.tokens_input = None
    label.tokens_output = None
    label.needs_review = False
    db.commit()

    _prime_label_processing(label, db)
    background_tasks.add_task(_process_label_balanced, label.id)
    log_action(
        user.id,
        "label_scan_retried",
        "label",
        label.id,
        detail=f"Retried label scan for {label.product.name}",
        request=request,
        context={"product_id": label.product.id},
    )
    return RedirectResponse(url=f"/labels/{label.id}?processing=1", status_code=302)


@router.get("/labels/{label_id}/status")
async def label_status_v2(label_id: int, request: Request, db: Session = Depends(get_db)):
    """JSON polling endpoint backed by persisted processing state."""
    user = require_user(request, db)
    if not user:
        return JSONResponse(_status_payload(None))

    job = _SCAN_JOBS.get(label_id)
    label = _owned_label_query(db, user).filter(LabelVersion.id == label_id).first()
    if not label:
        return JSONResponse(_status_payload(None))

    if job is not None and job.get("status") in {PROCESSING_QUEUED, PROCESSING_PROCESSING}:
        age = _time_mod.time() - job["started"]
        if age > SCAN_TIMEOUT_SECS:
            _set_job_state(job, status=PROCESSING_FAILED, step="timeout", error="Processing timed out")
            _update_processing_state(
                label,
                db,
                status=PROCESSING_FAILED,
                step="timeout",
                error="Processing timed out",
                finished_at=datetime.datetime.utcnow(),
            )

    if _scan_retry_allowed(label) and label.processing_status in {PROCESSING_QUEUED, PROCESSING_PROCESSING}:
        _update_processing_state(
            label,
            db,
            status=PROCESSING_FAILED,
            step=label.processing_step or "stale",
            error=label.processing_error or "Scan stalled before completion",
            finished_at=datetime.datetime.utcnow(),
        )

    return JSONResponse(_status_payload(label, job))


@router.get("/labels/{label_id}/status-legacy")
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
    label = _owned_label_query(db, user).filter(LabelVersion.id == label_id).first()
    if not label:
        return JSONResponse({"ready": False, "failed": True, "step": ""})
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
    if not label or not label.product or (
        label.product.account_id and label.product.account_id != get_account_id(user)
    ) or (
        not label.product.account_id and label.product.user_id != user.id
    ):
        return RedirectResponse(url="/products")

    existing_report = db.query(ComplianceReport).filter(
        ComplianceReport.label_version_id == label_id
    ).first()
    if request.query_params.get("checker_done") == "1" and existing_report:
        return RedirectResponse(url=f"/reports/{existing_report.id}", status_code=302)

    summary = summarize_checks(label.checks)
    score = summary["score"]
    critical = calculate_critical_score(label.checks) if label.checks else {"critical_pass": True, "critical_score": 100, "critical_failures": 0}
    violation_summary = get_violation_summary(label.checks) if label.checks else {}
    verdict = build_verdict(score, critical["critical_failures"]) if score is not None else None
    status_payload = _status_payload(label)
    processing = label.processing_status in {PROCESSING_QUEUED, PROCESSING_PROCESSING}
    scan_failed = label.processing_status == PROCESSING_FAILED
    can_rescan = _scan_source_available(label)

    # Group checks by result
    failed = [c for c in label.checks if c.result == CheckResult.FAIL]
    warnings = [c for c in label.checks if c.result == CheckResult.WARNING]
    passed = [c for c in label.checks if c.result == CheckResult.PASS]

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
        "processing": processing,
        "scan_failed": scan_failed,
        "scan_status": status_payload,
        "can_rescan": can_rescan,
        "verdict": verdict,
        "summary": summary,
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

    label = _owned_label_query(db, user).filter(LabelVersion.id == label_id).first()
    if not label or not label.product:
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

    label = _owned_label_query(db, user).filter(LabelVersion.id == label_id).first()
    if not label or not label.product:
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
    if not can_upload_labels(user):
        return JSONResponse({"detail": "Read-only role"}, status_code=403)

    label = _owned_label_query(db, user).filter(LabelVersion.id == label_id).first()
    if not label or not label.product:
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
        critical_failures = calculate_critical_score(checks)["critical_failures"]
        existing_report.verdict = build_verdict(score, critical_failures)
        db.commit()

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "label_fields_edited", "label", label_id,
                   detail=f"Edited extraction fields for {label.product.name}, new score: {score}%")
    except Exception:
        pass

    return JSONResponse({"success": True, "score": score})
