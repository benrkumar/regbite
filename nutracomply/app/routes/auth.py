from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from jose import JWTError, jwt
import bcrypt

from app.database import get_db
from app.models import (
    User, Product, LabelVersion, ComplianceCheck, Alert,
    ComplianceRule, CheckResult, AlertType, AlertStatus, Severity, UserRole
)
from app.config import get_settings

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _validate_password(password: str) -> str | None:
    """Return error message if password is too weak, else None.
    Delegates to the shared policy in utils/password.py."""
    from app.utils.password import validate_password
    return validate_password(password)


def create_access_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({**data, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


def get_current_user_from_cookie(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if not email:
            return None
        user = db.query(User).filter(User.email == email).first()
        if user and not user.is_active:
            return None
        return user
    except JWTError:
        return None


def _seed_demo_products(user: User, db: Session):
    """Create 5 demo products with synthetic compliance data for new users."""
    rules = {r.rule_code: r for r in db.query(ComplianceRule).filter(ComplianceRule.active).all()}
    if not rules:
        return

    # All rule codes
    demos = [
        {
            "name": "Omega-3 Fish Oil 1000mg",
            "sku": "OFO-1000-60",
            "category": "Health Supplement",
            "description": "Premium Omega-3 fatty acids from deep-sea fish oil. 60 soft gel capsules.",
            "failing_codes": [],
            "extraction": {
                "product_name": "Omega-3 Fish Oil 1000mg",
                "product_type_declaration": "HEALTH SUPPLEMENT",
                "fssai_license_number": "10019042000241",
                "net_quantity": "60 Softgel Capsules",
                "serving_size": "1 Softgel Capsule daily",
                "manufacturing_date": "01/2025",
                "expiry_date": "12/2027",
                "batch_number": "OFO-B250110",
                "manufacturer_details": "HealthFirst Labs Pvt. Ltd., Plot 12, Pharma Zone, Baddi, HP - 173205",
                "country_of_origin": "India",
                "storage_conditions": "Store in a cool, dry place below 25°C. Keep out of direct sunlight.",
                "target_consumer": "Adults above 18 years",
                "veg_nonveg_mark": "NON-VEG",
                "ingredient_list": ["Fish Oil (Sardine, Anchovy)", "Gelatin (Bovine)", "Glycerin", "Purified Water"],
                "nutritional_table": [
                    {"nutrient": "Energy", "per_serving": "9 kcal", "per_100g": "900 kcal", "rda_percent": "0.45%"},
                    {"nutrient": "Total Fat", "per_serving": "1g", "per_100g": "100g", "rda_percent": "1.5%"},
                    {"nutrient": "EPA (Eicosapentaenoic Acid)", "per_serving": "180mg", "per_100g": "18g", "rda_percent": "*"},
                    {"nutrient": "DHA (Docosahexaenoic Acid)", "per_serving": "120mg", "per_100g": "12g", "rda_percent": "*"},
                ],
                "rda_percentages": True,
                "health_claims": ["Supports heart health", "Helps maintain healthy cholesterol levels"],
                "warnings": ["NOT FOR MEDICINAL USE", "not to exceed the stated recommended daily usage", "Keep out of reach of children", "Consult your doctor if pregnant or nursing"],
                "allergen_declarations": ["Contains: Fish"],
                "not_for_medicinal_use": True,
                "consult_doctor_advisory": True,
                "keep_out_of_reach_children": True,
                "not_exceed_daily_usage_advisory": True,
            },
        },
        {
            "name": "Ashwagandha KSM-66 500mg",
            "sku": "ASH-500-30",
            "category": "Ayurvedic Supplement",
            "description": "Clinically studied Ashwagandha root extract standardised to 5% withanolides.",
            "failing_codes": ["FSSAI-NUTRA-FORMAT-002", "FSSAI-NUTRA-WARN-003", "FSSAI-NUTRA-LBL-016", "FSSAI-NUTRA-ING-010"],
            "extraction": {
                "product_name": "Ashwagandha KSM-66 500mg",
                "product_type_declaration": "HEALTH SUPPLEMENT",
                "fssai_license_number": "10019042000318",
                "net_quantity": "30 Vegetarian Capsules",
                "serving_size": "1 capsule twice daily",
                "manufacturing_date": "03/2025",
                "expiry_date": "02/2028",
                "batch_number": "ASH-B250301",
                "manufacturer_details": "Vedic Wellness Pvt. Ltd., MIDC Industrial Area, Pune - 411019",
                "country_of_origin": "India",
                "storage_conditions": "Store below 30°C in a dry place. Keep out of reach of children.",
                "target_consumer": None,
                "veg_nonveg_mark": "VEG",
                "ingredient_list": ["Ashwagandha Root Extract (KSM-66, 5% Withanolides)", "Microcrystalline Cellulose", "Magnesium Stearate"],
                "nutritional_table": [
                    {"nutrient": "Energy", "per_serving": "2 kcal", "per_100g": "200 kcal", "rda_percent": "0.1%"},
                    {"nutrient": "Ashwagandha Extract", "per_serving": "500mg", "per_100g": "50g", "rda_percent": "*"},
                ],
                "rda_percentages": True,
                "health_claims": ["Supports stress management", "Helps improve energy and vitality"],
                "warnings": ["NOT FOR MEDICINAL USE", "not to exceed the stated recommended daily usage", "Keep out of reach of children", "Consult your doctor if pregnant or nursing"],
                "allergen_declarations": [],
                "not_for_medicinal_use": True,
                "consult_doctor_advisory": True,
                "keep_out_of_reach_children": True,
                "not_exceed_daily_usage_advisory": True,
            },
        },
        {
            "name": "Probiotic Complex 10B CFU",
            "sku": "PRB-10B-30",
            "category": "Digestive Health",
            "description": "Multi-strain probiotic formula with 10 billion CFU for gut health.",
            "failing_codes": [
                "FSSAI-NUTRA-LBL-002",   # CRITICAL: NOT FOR MEDICINAL USE missing
                "FSSAI-NUTRA-LBL-008",   # HIGH: RDA% not declared
                "FSSAI-NUTRA-LBL-013",   # HIGH: batch number missing
                "FSSAI-NUTRA-LBL-017",   # HIGH: manufacturing date missing
                "FSSAI-NUTRA-WARN-003",  # MEDIUM: side effects not declared
                "FSSAI-NUTRA-WARN-004",  # MEDIUM: pregnancy warning missing
                "FSSAI-NUTRA-FORMAT-002",# MEDIUM: font size
                "FSSAI-NUTRA-LBL-016",   # MEDIUM: target consumer missing
                "FSSAI-NUTRA-ING-009",   # HIGH: ingredient approval not verified
                "FSSAI-NUTRA-ING-010",   # MEDIUM: Vit D source
            ],
            "extraction": {
                "product_name": "Probiotic Complex 10B CFU",
                "product_type_declaration": "HEALTH SUPPLEMENT",
                "fssai_license_number": "10019042000422",
                "net_quantity": "30 Capsules",
                "serving_size": "1 capsule daily with water",
                "manufacturing_date": None,
                "expiry_date": "06/2027",
                "batch_number": None,
                "manufacturer_details": "Microbiome Health Pvt. Ltd., Sector 8, Gurgaon - 122001",
                "country_of_origin": "India",
                "storage_conditions": "Refrigerate after opening. Keep away from heat and moisture.",
                "target_consumer": None,
                "veg_nonveg_mark": "VEG",
                "ingredient_list": ["Lactobacillus acidophilus", "Bifidobacterium longum", "Lactobacillus rhamnosus", "FOS (Prebiotic Fiber)", "HPMC Capsule"],
                "nutritional_table": [
                    {"nutrient": "Energy", "per_serving": "0 kcal", "per_100g": "0 kcal", "rda_percent": None},
                    {"nutrient": "Probiotic Blend", "per_serving": "10 Billion CFU", "per_100g": "*", "rda_percent": None},
                ],
                "rda_percentages": False,
                "health_claims": ["Supports digestive health", "Maintains healthy gut flora"],
                "warnings": ["not to exceed the stated recommended daily usage", "Keep out of reach of children"],
                "allergen_declarations": ["Contains: Milk (traces)"],
                "not_for_medicinal_use": False,
                "consult_doctor_advisory": False,
                "keep_out_of_reach_children": True,
                "not_exceed_daily_usage_advisory": True,
            },
        },
        {
            "name": "Protein Isolate 25g",
            "sku": "PRI-25-1KG",
            "category": "Sports Nutrition",
            "description": "Whey protein isolate with 25g protein per serving for muscle recovery.",
            "failing_codes": [
                "FSSAI-NUTRA-CLAIM-001",  # CRITICAL: disease treatment claim
                "FSSAI-NUTRA-CLAIM-002",  # CRITICAL: disease prevention claim
                "FSSAI-NUTRA-LBL-003",    # CRITICAL: FSSAI license invalid format
                "FSSAI-NUTRA-LBL-008",    # HIGH: RDA%
                "FSSAI-NUTRA-LBL-013",    # HIGH: batch
                "FSSAI-NUTRA-LBL-017",    # HIGH: mfg date
                "FSSAI-NUTRA-QTY-001",    # HIGH: active ingredient qty
                "FSSAI-NUTRA-QTY-002",    # HIGH: energy value
                "FSSAI-NUTRA-WARN-003",   # MEDIUM: side effects
                "FSSAI-NUTRA-WARN-004",   # MEDIUM: pregnancy
                "FSSAI-NUTRA-FORMAT-002", # MEDIUM: font
                "FSSAI-NUTRA-LBL-016",    # MEDIUM: target consumer
                "FSSAI-NUTRA-CLAIM-005",  # HIGH: substantiation
                "FSSAI-NUTRA-ALLERGEN-001",# HIGH: allergen
                "FSSAI-NUTRA-ING-009",    # HIGH: ingredient approval
                "FSSAI-NUTRA-ING-010",    # MEDIUM: vit D source
            ],
            "extraction": {
                "product_name": "Protein Isolate 25g",
                "product_type_declaration": "HEALTH SUPPLEMENT",
                "fssai_license_number": "FSSAI-XXX-001",  # invalid format
                "net_quantity": "1 kg (33 Servings)",
                "serving_size": "30g (1 scoop)",
                "manufacturing_date": None,
                "expiry_date": "09/2026",
                "batch_number": None,
                "manufacturer_details": "ProSports Nutrition, A-42, Industrial Estate, Mumbai - 400001",
                "country_of_origin": "India",
                "storage_conditions": "Store in a cool, dry place.",
                "target_consumer": None,
                "veg_nonveg_mark": "NON-VEG",
                "ingredient_list": ["Whey Protein Isolate", "Cocoa Powder", "Sucralose", "Soy Lecithin"],
                "nutritional_table": [],
                "rda_percentages": False,
                "health_claims": [
                    "Repairs muscle damage",
                    "Treats muscle soreness and inflammation",
                    "Clinically proven to cure protein deficiency"
                ],
                "warnings": ["NOT FOR MEDICINAL USE", "not to exceed the stated recommended daily usage", "Keep out of reach of children"],
                "allergen_declarations": [],
                "not_for_medicinal_use": True,
                "consult_doctor_advisory": False,
                "keep_out_of_reach_children": True,
                "not_exceed_daily_usage_advisory": True,
            },
        },
        {
            "name": "MultiVitamin Pro (Women)",
            "sku": "MVP-W-60",
            "category": "Vitamin & Mineral Supplement",
            "description": "Complete multivitamin with 23 essential nutrients formulated for women.",
            "failing_codes": [
                "FSSAI-NUTRA-LBL-002",    # CRITICAL: NOT FOR MEDICINAL USE
                "FSSAI-NUTRA-LBL-003",    # CRITICAL: FSSAI license
                "FSSAI-NUTRA-LBL-005",    # CRITICAL: net quantity
                "FSSAI-NUTRA-LBL-007",    # CRITICAL: nutritional table
                "FSSAI-NUTRA-LBL-008",    # HIGH: RDA%
                "FSSAI-NUTRA-LBL-011",    # CRITICAL: expiry date
                "FSSAI-NUTRA-LBL-012",    # CRITICAL: manufacturer
                "FSSAI-NUTRA-LBL-013",    # HIGH: batch
                "FSSAI-NUTRA-LBL-014",    # MEDIUM: storage
                "FSSAI-NUTRA-LBL-015",    # HIGH: veg/nonveg
                "FSSAI-NUTRA-LBL-016",    # MEDIUM: target consumer
                "FSSAI-NUTRA-LBL-017",    # HIGH: mfg date
                "FSSAI-NUTRA-WARN-001",   # HIGH: keep out of reach
                "FSSAI-NUTRA-WARN-002",   # MEDIUM: consult doctor
                "FSSAI-NUTRA-WARN-003",   # MEDIUM: side effects
                "FSSAI-NUTRA-WARN-004",   # MEDIUM: pregnancy
                "FSSAI-NUTRA-QTY-001",    # HIGH: active ingredient qty
                "FSSAI-NUTRA-QTY-002",    # HIGH: energy
                "FSSAI-NUTRA-FORMAT-002", # MEDIUM: font
                "FSSAI-NUTRA-ALLERGEN-001",# HIGH: allergen
                "FSSAI-NUTRA-CLAIM-005",  # HIGH: substantiation
                "FSSAI-NUTRA-ING-010",    # MEDIUM: vit D source
            ],
            "extraction": {
                "product_name": "MultiVitamin Pro Women",
                "product_type_declaration": "HEALTH SUPPLEMENT",
                "fssai_license_number": None,
                "net_quantity": None,
                "serving_size": "1 tablet daily",
                "manufacturing_date": None,
                "expiry_date": None,
                "batch_number": None,
                "manufacturer_details": None,
                "country_of_origin": "India",
                "storage_conditions": None,
                "target_consumer": None,
                "veg_nonveg_mark": None,
                "ingredient_list": ["Vitamin A", "Vitamin C", "Vitamin D3", "Vitamin E", "B-Complex", "Zinc", "Iron", "Calcium"],
                "nutritional_table": [],
                "rda_percentages": False,
                "health_claims": ["Supports overall health and wellbeing"],
                "warnings": [],
                "allergen_declarations": [],
                "not_for_medicinal_use": False,
                "consult_doctor_advisory": False,
                "keep_out_of_reach_children": False,
                "not_exceed_daily_usage_advisory": False,
            },
        },
    ]

    for demo in demos:
        product = Product(
            user_id=user.id,
            name=demo["name"],
            sku=demo["sku"],
            category=demo["category"],
            description=demo["description"],
        )
        db.add(product)
        db.flush()

        label = LabelVersion(
            product_id=product.id,
            file_path=f"demo/{product.id}/synthetic_label.jpg",
            file_name="synthetic_label.jpg",
            file_type="image",
            uploaded_at=datetime.utcnow() - timedelta(days=2),
            ocr_raw_text="[Demo product — synthetic label data]",
            extraction_json=demo["extraction"],
            extraction_confidence=0.95,
            is_current=True,
        )
        db.add(label)
        db.flush()

        failing_set = set(demo["failing_codes"])
        for code, rule in rules.items():
            if code in failing_set:
                result = CheckResult.FAIL
                msg = f"Required field missing or invalid: {rule.description}"
                remediation = rule.remediation_template or ""
            else:
                result = CheckResult.PASS
                msg = "Check passed"
                remediation = ""

            check = ComplianceCheck(
                label_version_id=label.id,
                rule_id=rule.id,
                result=result,
                actual_value=None if code in failing_set else "Present",
                message=msg,
                remediation=remediation,
                checked_at=datetime.utcnow() - timedelta(days=2),
            )
            db.add(check)

        # Create alert for flagged products (>3 failures)
        if len(failing_set) > 3:
            total = len(rules)
            passed = total - len(failing_set)
            # Use severity-weighted scoring for alert messages
            from app.services.compliance_engine import calculate_compliance_score as _calc
            demo_checks = db.query(ComplianceCheck).filter(
                ComplianceCheck.label_version_id == label.id
            ).all()
            score = _calc(demo_checks) if demo_checks else round((passed / total) * 100) if total else 0
            critical_count = sum(1 for c in failing_set if rules.get(c) and rules[c].severity == Severity.CRITICAL)
            high_count = sum(1 for c in failing_set if rules.get(c) and rules[c].severity == Severity.HIGH)

            sev = Severity.CRITICAL if critical_count > 0 else Severity.HIGH
            violations = [
                {
                    "rule_code": code,
                    "severity": rules[code].severity if code in rules else "HIGH",
                    "message": f"Non-compliant: {rules[code].description}" if code in rules else code,
                    "remediation": rules[code].remediation_template if code in rules else "",
                }
                for code in list(failing_set)[:5]
            ]
            alert = Alert(
                product_id=product.id,
                label_version_id=label.id,
                alert_type=AlertType.LABEL_VIOLATION,
                severity=sev,
                title=f"Label compliance issues detected — {len(failing_set)} violation(s)",
                message=(
                    f"{demo['name']} has a compliance score of {score}% with "
                    f"{critical_count} critical and {high_count} high severity violations that require immediate attention."
                ),
                rule_violations=violations,
                status=AlertStatus.UNREAD,
            )
            db.add(alert)

    db.commit()


def _stashed_file(request: Request, db: Session):
    """
    Describe a label the visitor uploaded before signing up, so the auth pages
    can reassure them it is still held. Returns None when there is nothing
    claimable — never echo a stale filename.
    """
    try:
        from app.services.stash_service import read_stash, STASH_COOKIE
        row = read_stash(db, request.cookies.get(STASH_COOKIE))
        if not row:
            return None
        return {
            "name": row.file_name,
            "size_kb": max(1, (row.byte_size or 0) // 1024),
        }
    except Exception:
        return None


def _claim_target(request: Request, db: Session, user, fallback: str) -> tuple[str, bool]:
    """
    Claim any pending anonymous upload for `user`.

    Returns (redirect_target, claimed). Never raises — a stash failure must not
    break a sign-in or a signup.
    """
    try:
        from app.services.stash_service import claim_stash, STASH_COOKIE
        label = claim_stash(db, request.cookies.get(STASH_COOKIE), user)
        if label:
            return f"/checker/resume/{label.id}", True
    except Exception as e:
        print(f"[auth] stash claim failed: {e}")
    return fallback, False


@router.get("/login")
async def login_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "stashed_file": _stashed_file(request, db),
    })


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        from app.services.rate_limiter import limiter
        client_ip = request.client.host if request.client else "unknown"
        # Rate limit by both IP and email to prevent brute-force on specific accounts
        rate_key = f"{client_ip}:{email.lower().strip()}"
        allowed, retry_after = limiter.check("login", rate_key, limit=5, window=300)  # 5 per 5 min
        if not allowed:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": f"Too many login attempts. Please wait {retry_after} seconds.",
            }, status_code=429)
    except Exception:
        pass  # fail open

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    if not user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Your account has been deactivated. Please contact support."
        })

    token = create_access_token({"sub": user.email})
    # Someone who uploaded anonymously and already has an account arrives here,
    # not at /register — this is roughly half the traffic on that path.
    target, claimed = _claim_target(request, db, user, "/dashboard")
    response = RedirectResponse(url=target, status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=settings.access_token_expire_minutes * 60)
    if claimed:
        from app.services.stash_service import clear_stash_cookie
        clear_stash_cookie(response)
    try:
        from app.services.activity_service import log_action
        log_action(user.id, "login", detail=f"User {user.email} logged in", ip_address=request.client.host if request.client else None)
    except Exception:
        pass
    return response


@router.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    try:
        from app.services.activity_service import log_action
        log_action(user.id if user else None, "logout")
    except Exception:
        pass
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.get("/register")
async def register_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "error": None,
        "stashed_file": _stashed_file(request, db),
    })


@router.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    agree_terms: str = Form(None),
    db: Session = Depends(get_db),
):
    # Validate terms agreement
    if not agree_terms:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "You must agree to the Terms of Service and Privacy Policy to create an account.",
        })

    # Check if email already taken
    existing = db.query(User).filter(User.email == email.lower().strip()).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "An account with that email already exists. Please sign in.",
        })

    pw_error = _validate_password(password)
    if pw_error:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": pw_error,
        })

    is_admin = bool(settings.admin_email and email.lower().strip() == settings.admin_email.lower().strip())

    user = User(
        name=name.strip(),
        email=email.lower().strip(),
        hashed_password=hash_password(password),
        is_admin=is_admin,
        role=UserRole.SUPER_ADMIN if is_admin else UserRole.ACCOUNT_ADMIN,
        is_active=True,
        notification_emails=[],
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create 14-day Growth trial subscription (Growth-level access during trial)
    try:
        from app.models import Subscription, SubscriptionStatus, PlanType
        trial_end = datetime.utcnow() + timedelta(days=14)
        trial_sub = Subscription(
            user_id=user.id,
            plan=PlanType.GROWTH,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=trial_end,
            current_period_start=datetime.utcnow(),
            current_period_end=trial_end,
        )
        user.plan = PlanType.GROWTH  # sync denormalized field for fast lookups
        db.add(trial_sub)
        db.commit()
    except Exception as e:
        print(f"[register] Subscription seed failed: {e}")

    # Seed demo products for new regular users
    try:
        _seed_demo_products(user, db)
    except Exception as e:
        print(f"[register] Demo product seed failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass

    # Send welcome email
    try:
        from app.services.notification import send_welcome_email
        send_welcome_email(user)
    except Exception:
        pass

    token = create_access_token({"sub": user.email})
    # Claim any anonymous upload now that the account exists. Wrapped so a stash
    # problem can never fail a signup that already committed.
    target, claimed = _claim_target(request, db, user, "/onboarding")
    response = RedirectResponse(url=target, status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=settings.access_token_expire_minutes * 60)
    if claimed:
        from app.services.stash_service import clear_stash_cookie
        clear_stash_cookie(response)
    return response
