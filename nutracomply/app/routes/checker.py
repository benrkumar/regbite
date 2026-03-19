"""
Form-First Compliance Checker
Allows users to input product details manually and run a compliance check
without needing to upload a label image.
"""
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import (
    Product, LabelVersion, ComplianceRule, ComplianceCheck, CheckResult,
    Alert, AlertStatus, Severity
)

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
        return RedirectResponse(url="/login")

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("checker.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "categories": PRODUCT_CATEGORIES,
        "target_groups": TARGET_GROUPS,
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
        return RedirectResponse(url="/login")

    try:
        from app.services.rate_limiter import limiter
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check("checker", client_ip, limit=20, window=3600)  # 20/hr
        if not allowed:
            return RedirectResponse(url=f"/checker?error=Rate+limit+exceeded.+Try+again+in+{retry_after}+seconds.", status_code=302)
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
    product = Product(
        user_id=user.id,
        name=product_name,
        category=category,
        description=f"Checked via Compliance Checker on {datetime.utcnow().strftime('%d %b %Y')}",
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
