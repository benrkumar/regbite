"""
Form-First Compliance Checker
Allows users to input product details manually or upload a label image
and run a compliance check without needing to create a product first.
"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import (
    Product, LabelVersion, ComplianceRule, ComplianceCheck, CheckResult,
    Alert, AlertStatus
)
from app.config import get_settings
from app.utils.alerts import get_unread_alert_count

router = APIRouter(prefix="/checker")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PRODUCT_CATEGORIES = [
    "Health Supplement",
    "Sports Nutrition",
    "Herbal/Ayurvedic",
    "Functional Food",
    "Medical Nutrition",
    "Infant Nutrition",
    "Vitamin & Mineral Supplement",
    "Digestive Health",
    "Weight Management",
    "Other",
]

TARGET_GROUPS = [
    "General population",
    "Adults (18+)",
    "Women",
    "Men",
    "Athletes / Sports persons",
    "Elderly (60+)",
    "Children (5-12)",
    "Pregnant / Nursing women",
]


@router.get("")
async def checker_form(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    unread_alerts = get_unread_alert_count(user, db)

    return templates.TemplateResponse("checker.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "categories": PRODUCT_CATEGORIES,
        "target_groups": TARGET_GROUPS,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/run")
async def run_check(
    request: Request,
    product_name: str = Form(...),
    category: str = Form(...),
    ingredients: str = Form(...),
    label_claims: str = Form(""),
    manufacturing_origin: str = Form("India"),
    target_consumer: str = Form(""),
    fssai_license: str = Form(""),
    net_quantity: str = Form(""),
    batch_number: str = Form(""),
    manufacturing_date: str = Form(""),
    expiry_date: str = Form(""),
    has_nutritional_table: str = Form(""),
    has_veg_mark: str = Form(""),
    has_not_medicinal_use: str = Form(""),
    has_consult_doctor: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    try:
        from app.services.rate_limiter import limiter
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check("checker", client_ip, limit=20, window=3600)  # 20/hr
        if not allowed:
            return RedirectResponse(url=f"/checker?error=Rate+limit+exceeded.+Try+again+in+{retry_after}+seconds.", status_code=302)
    except Exception:
        pass

    # Quota check
    try:
        from app.services.quota_service import check_scan_limit
        allowed, quota_msg = check_scan_limit(user, db)
        if not allowed:
            from urllib.parse import quote
            return RedirectResponse(url=f"/checker?msg={quote(quota_msg)}&type=error", status_code=302)
    except Exception:
        pass

    # Build extraction_json from form data (same structure as OCR extraction)
    ingredient_list = [i.strip() for i in ingredients.split(",") if i.strip()]
    health_claims = [c.strip() for c in label_claims.split(",") if c.strip()] if label_claims else []

    extraction_json = {
        "product_name": product_name,
        "product_type_declaration": "HEALTH SUPPLEMENT",
        "fssai_license_number": fssai_license or None,
        "net_quantity": net_quantity or None,
        "serving_size": None,
        "manufacturing_date": manufacturing_date or None,
        "expiry_date": expiry_date or None,
        "batch_number": batch_number or None,
        "manufacturer_details": None,
        "country_of_origin": manufacturing_origin,
        "storage_conditions": None,
        "target_consumer": target_consumer or None,
        "veg_nonveg_mark": "VEG" if has_veg_mark else None,
        "ingredient_list": ingredient_list,
        "nutritional_table": [{"nutrient": "See label", "per_serving": "*", "per_100g": "*", "rda_percent": "*"}] if has_nutritional_table else [],
        "rda_percentages": bool(has_nutritional_table),
        "health_claims": health_claims,
        "warnings": [],
        "allergen_declarations": [],
        "not_for_medicinal_use": bool(has_not_medicinal_use),
        "consult_doctor_advisory": bool(has_consult_doctor),
        "keep_out_of_reach_children": True,
        "not_exceed_daily_usage_advisory": True,
    }

    # Create Product + LabelVersion + run compliance
    # is_quick_check=True keeps this out of the product catalog, quota counts, and KB
    product = Product(
        user_id=user.id,
        name=product_name,
        category=category,
        description=f"Checked via Compliance Checker on {datetime.utcnow().strftime('%d %b %Y')}",
        is_quick_check=True,
    )
    db.add(product)
    db.flush()

    label = LabelVersion(
        product_id=product.id,
        file_path=f"checker/{product.id}/manual_input.json",
        file_name="manual_input.json",
        file_type="json",
        ocr_raw_text="[Manual input via Compliance Checker]",
        extraction_json=extraction_json,
        extraction_confidence=1.0,
        is_current=True,
    )
    db.add(label)
    db.flush()

    # Run compliance engine
    try:
        from app.services.compliance_engine import run_compliance_check
        run_compliance_check(label, db)
    except Exception as e:
        print(f"[checker] Compliance engine error: {e}")
        # Fall back to basic rule checking
        _run_basic_checks(label, extraction_json, db)

    db.commit()
    db.refresh(label)

    # Feed into LLM knowledge base
    try:
        from app.routes.products import _feed_product_to_llm
        _feed_product_to_llm(product.id, db)
    except Exception as e:
        print(f"[checker] LLM feed error: {e}")

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "compliance_checked", "product", product.id, detail=f"Checker run for {product_name}")
    except Exception:
        pass

    # Generate report
    try:
        from app.services.report_service import get_or_create_report
        _ = label.checks
        for c in label.checks:
            _ = c.rule
        report = get_or_create_report(db, user.id, product.id, label.id)
        return RedirectResponse(url=f"/reports/{report.id}", status_code=302)
    except Exception as e:
        print(f"[checker] Report generation error: {e}")
        return RedirectResponse(url=f"/labels/{label.id}", status_code=302)


from app.utils.file_validation import ALLOWED_EXTENSIONS, validate_file_magic

# Families that a claimed suffix must agree with, so a .pdf-named JPEG is
# rejected rather than silently accepted.
_EXT_FAMILY = {
    ".jpg": "jpg", ".jpeg": "jpg",
    ".png": "png",
    ".pdf": "pdf",
    ".tif": "tiff", ".tiff": "tiff",
    ".webp": "webp",
}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _wants_json(request: Request) -> bool:
    """The landing uploader sets this so it can render inline state instead of
    being navigated away by a redirect."""
    return request.headers.get("x-rb-async") == "1"


def _upload_error(request: Request, message: str, status: int = 400):
    """JSON for the async uploader, a redirect for a native form POST."""
    from urllib.parse import quote
    if _wants_json(request):
        return JSONResponse({"ok": False, "detail": message}, status_code=status)
    return RedirectResponse(url=f"/?error={quote(message)}", status_code=302)


@router.post("/upload")
async def upload_check(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form("Health Supplement"),
    db: Session = Depends(get_db),
):
    """
    Upload a label image/PDF for a compliance check.

    Signed in  -> analyse immediately (unchanged behaviour).
    Anonymous  -> validate, stash the bytes server-side, and send them to sign
                  up. The stash is claimed on register/login and the analysis
                  resumes automatically, so the file is never lost.
    """
    user = get_current_user_from_cookie(request, db)

    if user is None:
        return await _stash_anonymous_upload(request, file, category, db)

    try:
        from app.services.rate_limiter import limiter
        allowed, retry_after = limiter.check(
            "checker_upload", _client_ip(request), limit=15, window=3600
        )
        if not allowed:
            return _upload_error(request, "Rate limit exceeded. Please try again shortly.", 429)
    except Exception:
        pass

    # Quota check
    try:
        from app.services.quota_service import check_scan_limit
        allowed, quota_msg = check_scan_limit(user, db)
        if not allowed:
            from urllib.parse import quote
            return RedirectResponse(url=f"/?error={quote(quota_msg)}", status_code=302)
    except Exception:
        pass

    # Validate file extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return _upload_error(request, "Unsupported file type.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        return _upload_error(request, "File too large (max 50 MB).", 413)

    # Validate file magic bytes (prevents disguised file uploads)
    detected_ext = validate_file_magic(content)
    if detected_ext is None or _EXT_FAMILY.get(detected_ext) != _EXT_FAMILY.get(suffix):
        return _upload_error(
            request,
            "File type not recognised. Please upload a valid image or PDF.",
        )

    # Save file
    settings = get_settings()
    upload_dir = Path(settings.upload_dir) / "checker"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}{suffix}"
    file_path = upload_dir / file_name

    with open(file_path, "wb") as f:
        f.write(content)

    # Create product + label version (is_quick_check=True keeps it ephemeral)
    product = Product(
        user_id=user.id,
        name=file.filename.rsplit(".", 1)[0][:80] or "Uploaded Label",
        category=category,
        description=f"Label uploaded via Quick Check on {datetime.utcnow().strftime('%d %b %Y')}",
        is_quick_check=True,
    )
    db.add(product)
    db.flush()

    label = LabelVersion(
        product_id=product.id,
        file_path=str(file_path),
        file_name=file.filename,
        file_type="pdf" if suffix == ".pdf" else "image",
        is_current=True,
    )
    db.add(label)
    db.commit()
    db.refresh(label)

    # Run OCR + extraction + compliance in background via the same pipeline as /products upload
    try:
        from app.routes.labels import _process_label
        _process_label(label.id)
    except Exception as e:
        print(f"[checker/upload] Processing error: {e}")

    # Try to generate report
    try:
        db.refresh(label)
        from app.services.report_service import get_or_create_report
        _ = label.checks
        for c in label.checks:
            _ = c.rule
        report = get_or_create_report(db, user.id, product.id, label.id)
        return RedirectResponse(url=f"/reports/{report.id}", status_code=302)
    except Exception as e:
        print(f"[checker/upload] Report error: {e}")
        return RedirectResponse(url=f"/labels/{label.id}", status_code=302)


async def _stash_anonymous_upload(
    request: Request,
    file: UploadFile,
    category: str,
    db: Session,
):
    """
    Hold an anonymous visitor's label until they have an account.

    This is the app's only unauthenticated byte-storing path, so every control
    below runs BEFORE anything is persisted, and the rate limiter is allowed to
    deny (it fails closed; wrapping it in try/except would turn that into
    fail-open, which is what the authenticated path above unfortunately does).
    """
    from app.services import stash_service as stash

    # Opportunistic sweep — cheap and indexed.
    stash.purge_expired(db, limit=200)

    # 1. Size, before reading the body. Starlette spools UploadFile to disk
    #    above ~1 MB, so a huge POST would fill the container disk before any
    #    post-read size check could fire.
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > stash.STASH_MAX_BYTES + 8192:  # small allowance for the envelope
        return _upload_error(request, "File too large. The free check accepts up to 10 MB.", 413)

    # 2. Rate limits. No try/except swallow: a limiter error must deny.
    from app.services.rate_limiter import limiter
    ip = _client_ip(request)
    for ns, lim, win, msg in (
        ("anon_upload_ip", 3, 3600, "You've used the free check a few times. Create an account to keep going."),
        ("anon_upload_ip_day", 8, 86400, "Daily free-check limit reached. Create an account to keep going."),
    ):
        allowed, _retry = limiter.check(ns, ip, limit=lim, window=win)
        if not allowed:
            return _upload_error(request, msg, 429)
    allowed, _retry = limiter.check("anon_upload_global", "all", limit=300, window=3600)
    if not allowed:
        return _upload_error(
            request,
            "The free check is unusually busy right now. Create an account to run it immediately.",
            429,
        )

    # 3. Extension allowlist.
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return _upload_error(request, "Unsupported file type. Upload a JPG, PNG, WebP, TIFF or PDF.")

    # 4. Read with a running cap, in case Content-Length lied or was absent.
    chunks, total = [], 0
    while True:
        chunk = await file.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > stash.STASH_MAX_BYTES:
            return _upload_error(request, "File too large. The free check accepts up to 10 MB.", 413)
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        return _upload_error(request, "That file appears to be empty.")

    # 5. Magic bytes, cross-checked against the claimed suffix.
    detected_ext = validate_file_magic(content)
    if detected_ext is None or _EXT_FAMILY.get(detected_ext) != _EXT_FAMILY.get(suffix):
        return _upload_error(request, "File type not recognised. Please upload a valid image or PDF.")

    # 6. Per-IP parked-row cap, so one visitor cannot park several large files.
    if stash.count_unclaimed_for_ip(db, stash.hash_ip(ip)) >= stash.PER_IP_UNCLAIMED_MAX:
        return _upload_error(
            request,
            "You already have a label waiting. Create your account to analyse it.",
            429,
        )

    # 7. Global unclaimed-bytes ceiling.
    if stash.unclaimed_bytes(db) + len(content) > stash.UNCLAIMED_BYTE_CEIL:
        return _upload_error(
            request,
            "The free check is unusually busy right now. Create an account to run it immediately.",
            429,
        )

    safe_name = Path(file.filename or "label").name[:255]
    raw_token = stash.create_stash(
        db,
        kind="file",
        file_bytes=content,
        file_name=safe_name,
        suffix=suffix,
        file_type="pdf" if suffix == ".pdf" else "image",
        category=category,
        ip=ip,
    )

    secure = request.url.scheme == "https"
    if _wants_json(request):
        resp = JSONResponse({
            "ok": True,
            "redirect": "/register?stashed=1",
            "file_name": safe_name,
        })
    else:
        # No JS: a native form POST just follows the redirect.
        resp = RedirectResponse(url="/register?stashed=1", status_code=302)
    stash.set_stash_cookie(resp, raw_token, secure=secure)
    return resp


@router.get("/resume/{label_id}")
async def resume_check(label_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Run the analysis on a label that was just claimed from an anonymous stash.

    Deliberately NOT /dashboard: main.py bounces users with
    onboarding_complete == False back to /onboarding, and we want a brand-new
    signup to see their report first. Their next /dashboard visit still routes
    them into the wizard.
    """
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    label = db.query(LabelVersion).filter(LabelVersion.id == label_id).first()
    if not label:
        return RedirectResponse(url="/dashboard", status_code=302)

    product = db.query(Product).filter(Product.id == label.product_id).first()
    if not product or product.user_id != user.id:
        return RedirectResponse(url="/dashboard", status_code=302)

    try:
        from app.routes.labels import _process_label
        _process_label(label.id)
    except Exception as e:
        print(f"[checker/resume] Processing error: {e}")
        return RedirectResponse(url=f"/labels/{label.id}?from=signup", status_code=302)

    try:
        db.refresh(label)
        from app.services.report_service import get_or_create_report
        _ = label.checks
        for c in label.checks:
            _ = c.rule
        report = get_or_create_report(db, user.id, product.id, label.id)
        return RedirectResponse(url=f"/reports/{report.id}?from=signup", status_code=302)
    except Exception as e:
        print(f"[checker/resume] Report error: {e}")
        return RedirectResponse(url=f"/labels/{label.id}?from=signup", status_code=302)


def _run_basic_checks(label: LabelVersion, extraction: dict, db: Session):
    """Basic rule-based checks when the main compliance engine fails."""
    rules = db.query(ComplianceRule).filter(ComplianceRule.active == True).all()

    for rule in rules:
        result = CheckResult.PASS
        msg = "Check passed"
        remediation = ""

        code = rule.rule_code

        # Check FSSAI license
        if "LBL-003" in code or "LBL-001" in code:
            fssai = extraction.get("fssai_license_number")
            if not fssai:
                result = CheckResult.FAIL
                msg = "FSSAI license number is missing"
                remediation = rule.remediation_template or "Add valid FSSAI license number"

        # Check mandatory label elements
        elif "LBL-002" in code:
            if not extraction.get("not_for_medicinal_use"):
                result = CheckResult.FAIL
                msg = "'NOT FOR MEDICINAL USE' declaration is missing"
                remediation = rule.remediation_template or ""

        elif "LBL-005" in code:
            if not extraction.get("net_quantity"):
                result = CheckResult.FAIL
                msg = "Net quantity declaration is missing"
                remediation = rule.remediation_template or ""

        elif "LBL-007" in code:
            if not extraction.get("nutritional_table"):
                result = CheckResult.WARNING
                msg = "Nutritional information table not provided"
                remediation = rule.remediation_template or ""

        elif "LBL-008" in code:
            if not extraction.get("rda_percentages"):
                result = CheckResult.WARNING
                msg = "%RDA values not declared in nutritional table"
                remediation = rule.remediation_template or ""

        elif "LBL-011" in code:
            if not extraction.get("expiry_date"):
                result = CheckResult.FAIL
                msg = "Best before / expiry date is missing"
                remediation = rule.remediation_template or ""

        elif "LBL-013" in code:
            if not extraction.get("batch_number"):
                result = CheckResult.WARNING
                msg = "Batch/lot number is missing"
                remediation = rule.remediation_template or ""

        elif "LBL-017" in code:
            if not extraction.get("manufacturing_date"):
                result = CheckResult.WARNING
                msg = "Manufacturing date is missing"
                remediation = rule.remediation_template or ""

        db.add(ComplianceCheck(
            label_version_id=label.id,
            rule_id=rule.id,
            result=result,
            actual_value=None if result == CheckResult.PASS else "Missing",
            message=msg,
            remediation=remediation,
            checked_at=datetime.utcnow(),
        ))
