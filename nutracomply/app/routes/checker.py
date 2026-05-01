"""
Workspace-authenticated compliance checker with ephemeral checker sessions.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import CheckerSession, ComplianceCheck, ComplianceRule, LabelVersion, Product, CheckResult
from app.routes.auth import get_current_user_from_cookie
from app.routes.labels import _prime_label_processing, _process_label_balanced
from app.services.access_control import can_mutate_products, can_run_checker, get_account_id
from app.services.alert_service import count_unread_alerts
from app.services.quota_service import check_product_limit, check_scan_limit
from app.services.upload_service import persist_upload_bytes, validate_upload_content

router = APIRouter(prefix="/checker")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
settings = get_settings()

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


def _require_checker_user(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user or not can_run_checker(user):
        return None
    return user


def _get_checker_user(request: Request, db: Session):
    return get_current_user_from_cookie(request, db)


def _session_query(db: Session, user):
    account_id = get_account_id(user)
    query = db.query(CheckerSession)
    if account_id:
        query = query.filter(CheckerSession.account_id == account_id)
    else:
        query = query.filter(CheckerSession.user_id == user.id)
    return query


def _create_session_record(db: Session, user, product: Product, label: LabelVersion | None, source_type: str, input_payload: dict) -> CheckerSession:
    session = CheckerSession(
        account_id=get_account_id(user),
        user_id=user.id,
        product_id=product.id if product else None,
        label_version_id=label.id if label else None,
        source_type=source_type,
        input_payload=input_payload,
    )
    db.add(session)
    db.flush()
    return session


@router.get("")
async def checker_form(request: Request, db: Session = Depends(get_db)):
    user = _get_checker_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_run_checker(user):
        return templates.TemplateResponse("permission_denied.html", {
            "request": request,
            "user": user,
            "unread_alerts": count_unread_alerts(db, user),
            "denied_title": "Checker access is limited to editing roles",
            "denied_message": "Your role can review existing reports, but only editors and account admins can run new checker sessions.",
            "back_url": "/reports",
            "back_label": "Back to Reports",
        }, status_code=403)

    return templates.TemplateResponse("checker.html", {
        "request": request,
        "user": user,
        "unread_alerts": count_unread_alerts(db, user),
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
    user = _get_checker_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_run_checker(user):
        return RedirectResponse(
            url="/reports?msg=Your+role+can+review+reports+but+cannot+run+new+checker+sessions.&type=error",
            status_code=302,
        )

    try:
        from app.services.rate_limiter import limiter
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check("checker", client_ip, limit=20, window=3600)
        if not allowed:
            return RedirectResponse(
                url=f"/checker?msg=Rate+limit+exceeded.+Try+again+in+{retry_after}+seconds.&type=error",
                status_code=302,
            )
    except Exception:
        pass

    ingredient_list = [item.strip() for item in ingredients.split(",") if item.strip()]
    health_claims = [item.strip() for item in label_claims.split(",") if item.strip()] if label_claims else []
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

    product = Product(
        account_id=get_account_id(user),
        user_id=user.id,
        name=product_name,
        category=category,
        description=f"Ephemeral checker session created on {datetime.utcnow().strftime('%d %b %Y')}",
        is_temporary=True,
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
        processing_status="ready",
        processing_step="manual",
        processing_finished_at=datetime.utcnow(),
        is_current=True,
    )
    db.add(label)
    db.flush()

    session = _create_session_record(db, user, product, label, "manual", extraction_json)

    try:
        from app.services.compliance_engine import run_compliance_check
        run_compliance_check(label, db)
    except Exception as exc:
        print(f"[checker] Compliance engine error: {exc}")
        _run_basic_checks(label, extraction_json, db)

    db.commit()
    db.refresh(label)

    try:
        from app.services.activity_service import log_action
        log_action(user.id, "compliance_checked", "checker_session", session.id, detail=f"Checker run for {product_name}")
    except Exception:
        pass

    try:
        from app.services.report_service import get_or_create_report
        _ = label.checks
        for check in label.checks:
            _ = check.rule
        report = get_or_create_report(db, user.id, product.id, label.id, checker_session_id=session.id)
        return RedirectResponse(url=f"/reports/{report.id}", status_code=302)
    except Exception as exc:
        print(f"[checker] Report generation error: {exc}")
        return RedirectResponse(url=f"/labels/{label.id}", status_code=302)


@router.post("/upload")
async def upload_check(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form("Health Supplement"),
    db: Session = Depends(get_db),
):
    user = _get_checker_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_run_checker(user):
        return RedirectResponse(
            url="/reports?msg=Your+role+can+review+reports+but+cannot+run+new+checker+sessions.&type=error",
            status_code=302,
        )

    try:
        from app.services.rate_limiter import limiter
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check("checker_upload", client_ip, limit=15, window=3600)
        if not allowed:
            return RedirectResponse(
                url=f"/checker?msg=Rate+limit+exceeded.+Try+again+in+{retry_after}+seconds.&type=error",
                status_code=302,
            )
    except Exception:
        pass

    try:
        content = await file.read()
        suffix = validate_upload_content(file.filename or "", content)
    except ValueError as exc:
        return RedirectResponse(url=f"/checker?msg={str(exc).replace(' ', '+')}&type=error", status_code=302)

    product = Product(
        account_id=get_account_id(user),
        user_id=user.id,
        name=file.filename.rsplit(".", 1)[0][:80] or "Uploaded Label",
        category=category,
        description=f"Ephemeral checker upload on {datetime.utcnow().strftime('%d %b %Y')}",
        is_temporary=True,
    )
    db.add(product)
    db.flush()

    file_path = persist_upload_bytes(settings.upload_dir, f"checker/{product.id}", suffix, content)
    label = LabelVersion(
        product_id=product.id,
        file_path=str(file_path),
        file_name=file.filename,
        file_type="pdf" if suffix == ".pdf" else "image",
        processing_status="queued",
        processing_step="queued",
        needs_review=False,
        is_current=True,
        file_data=content,
    )
    db.add(label)
    db.flush()

    session = _create_session_record(db, user, product, label, "upload", {"filename": file.filename, "category": category})
    db.commit()
    db.refresh(label)
    _prime_label_processing(label, db)
    background_tasks.add_task(_process_label_balanced, label.id)
    return RedirectResponse(url=f"/labels/{label.id}?processing=1&checker=1", status_code=302)


@router.post("/sessions/{session_id}/promote")
async def promote_checker_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_checker_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_run_checker(user):
        return RedirectResponse(
            url="/reports?msg=Your+role+can+review+reports+but+cannot+promote+checker+sessions.&type=error",
            status_code=302,
        )
    if not can_mutate_products(user):
        return RedirectResponse(url="/reports?msg=Read-only+role&type=error", status_code=302)

    session = _session_query(db, user).filter(CheckerSession.id == session_id).first()
    if not session or not session.product:
        return RedirectResponse(url="/reports?msg=Checker+session+not+found&type=error", status_code=302)
    if session.promoted_at:
        return RedirectResponse(url=f"/products/{session.promoted_product_id or session.product_id}", status_code=302)

    allowed_product, product_msg = check_product_limit(user, db)
    if not allowed_product:
        return RedirectResponse(url=f"/reports?msg={product_msg.replace(' ', '+')}&type=error", status_code=302)
    allowed_scan, scan_msg = check_scan_limit(user, db)
    if not allowed_scan:
        return RedirectResponse(url=f"/reports?msg={scan_msg.replace(' ', '+')}&type=error", status_code=302)

    session.product.is_temporary = False
    session.promoted_product_id = session.product.id
    session.promoted_at = datetime.utcnow()
    db.commit()

    try:
        from app.routes.products import _feed_product_to_llm
        _feed_product_to_llm(session.product.id, db)
    except Exception:
        pass

    return RedirectResponse(url=f"/products/{session.product.id}", status_code=302)


def _run_basic_checks(label: LabelVersion, extraction: dict, db: Session):
    rules = db.query(ComplianceRule).filter(ComplianceRule.active == True).all()

    for rule in rules:
        result = CheckResult.PASS
        message = "Check passed"
        remediation = ""
        code = rule.rule_code

        if "LBL-003" in code or "LBL-001" in code:
            if not extraction.get("fssai_license_number"):
                result = CheckResult.FAIL
                message = "FSSAI license number is missing"
                remediation = rule.remediation_template or "Add valid FSSAI license number"
        elif "LBL-002" in code:
            if not extraction.get("not_for_medicinal_use"):
                result = CheckResult.FAIL
                message = "'NOT FOR MEDICINAL USE' declaration is missing"
                remediation = rule.remediation_template or ""
        elif "LBL-005" in code:
            if not extraction.get("net_quantity"):
                result = CheckResult.FAIL
                message = "Net quantity declaration is missing"
                remediation = rule.remediation_template or ""
        elif "LBL-007" in code:
            if not extraction.get("nutritional_table"):
                result = CheckResult.WARNING
                message = "Nutritional information table not provided"
                remediation = rule.remediation_template or ""
        elif "LBL-008" in code:
            if not extraction.get("rda_percentages"):
                result = CheckResult.WARNING
                message = "%RDA values not declared in nutritional table"
                remediation = rule.remediation_template or ""
        elif "LBL-011" in code:
            if not extraction.get("expiry_date"):
                result = CheckResult.FAIL
                message = "Best before / expiry date is missing"
                remediation = rule.remediation_template or ""
        elif "LBL-013" in code:
            if not extraction.get("batch_number"):
                result = CheckResult.WARNING
                message = "Batch/lot number is missing"
                remediation = rule.remediation_template or ""
        elif "LBL-017" in code:
            if not extraction.get("manufacturing_date"):
                result = CheckResult.WARNING
                message = "Manufacturing date is missing"
                remediation = rule.remediation_template or ""

        db.add(ComplianceCheck(
            label_version_id=label.id,
            rule_id=rule.id,
            result=result,
            actual_value=None if result == CheckResult.PASS else "Missing",
            message=message,
            remediation=remediation,
            checked_at=datetime.utcnow(),
        ))
