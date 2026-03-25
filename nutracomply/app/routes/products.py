import uuid
import csv
import io
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, LabelVersion
from app.routes.auth import get_current_user_from_cookie
from app.config import get_settings

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

LABEL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".pdf", ".webp"}
SPREADSHEET_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ALL_ALLOWED = LABEL_EXTENSIONS | SPREADSHEET_EXTENSIONS


def require_user(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None
    return user


@router.get("/products")
async def products_list(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    products = (
        db.query(Product)
        .filter(Product.user_id == user.id, Product.is_active == True)
        .order_by(Product.created_at.desc())
        .all()
    )
    for p in products:
        _ = p.label_versions
        for lv in p.label_versions:
            _ = lv.checks

    return templates.TemplateResponse("products.html", {
        "request": request,
        "user": user,
        "products": products,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/products/add")
async def add_product(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    sku: str = Form(""),
    category: str = Form("Health Supplement"),
    description: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    # Quota check
    try:
        from app.services.quota_service import check_product_limit
        allowed, quota_msg = check_product_limit(user, db)
        if not allowed:
            from urllib.parse import quote
            return RedirectResponse(url=f"/products?msg={quote(quota_msg)}&type=error", status_code=302)
    except Exception:
        pass

    # ── If a CSV/Excel file was uploaded, handle as bulk import ──
    if file and file.filename:
        suffix = Path(file.filename).suffix.lower()

        if suffix in SPREADSHEET_EXTENSIONS:
            return await _handle_spreadsheet_upload(request, user, file, suffix, db)

        if suffix not in LABEL_EXTENSIONS:
            from urllib.parse import quote
            msg = f"Unsupported file type '{suffix}'. Use image/PDF for labels or CSV/Excel for bulk import."
            return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)

    # ── Create the product ──
    product = Product(
        user_id=user.id,
        name=name,
        sku=sku or None,
        category=category,
        description=description,
    )
    db.add(product)
    db.commit()

    # ── If an image/PDF was uploaded, attach as label and trigger processing ──
    if file and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix in LABEL_EXTENSIONS:
            label_version = await _save_label_file(file, suffix, product.id, db)
            background_tasks.add_task(_process_label_bg, label_version.id)
            try:
                from app.services.activity_service import log_action
                log_action(user.id, "label_uploaded", "label", label_version.id,
                           detail=f"Uploaded label for {product.name}")
            except Exception:
                pass
            return RedirectResponse(url=f"/labels/{label_version.id}?processing=1", status_code=302)

    return RedirectResponse(url=f"/products/{product.id}", status_code=302)


async def _save_label_file(file: UploadFile, suffix: str, product_id: int, db: Session) -> LabelVersion:
    """Save uploaded file to disk and create a LabelVersion record."""
    content = await file.read()

    # Reject files over 50 MB
    if len(content) > 50 * 1024 * 1024:
        raise ValueError("File too large (max 50 MB)")

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
    return label_version


def _process_label_bg(label_version_id: int):
    """Background: OCR → extract → compliance check → alerts → feed LLM.

    Token-saving: Stores extraction results permanently. On re-analysis,
    if confidence >= 0.85 the stored extraction is reused (zero API tokens).
    """
    from app.database import SessionLocal
    from app.services.ocr_service import extract_text_from_file
    from app.services.extraction_service import extract_label_data, extract_label_data_from_image
    from app.services.compliance_engine import run_compliance_check, calculate_compliance_score
    from app.models import Alert, AlertType, AlertStatus, CheckResult, Severity, Product

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

            try:
                from app.services.notification import send_alert_email
                product = db.query(Product).filter(Product.id == label_version.product_id).first()
                send_alert_email(alert, product)
            except Exception as e:
                print(f"[alert] Email failed: {e}")

        # Step 5: Feed product into LLM knowledge base
        try:
            _feed_product_to_llm(label_version.product_id, db)
        except Exception as e:
            print(f"[llm-feed] Error: {e}")

    except Exception as e:
        print(f"[process_label] Error: {e}")
        db.rollback()
    finally:
        db.close()


def _feed_product_to_llm(product_id: int, db):
    """Ingest/update this product's data + extraction into the Products LLM KB.

    Stores the full extraction JSON, compliance results, and OCR text so the
    LLM can reference all learned data without making additional API calls.
    This is the 'learning' step — every scan result is permanently stored.
    """
    import json as _json
    from app.models import KBDocument, KBChunk, KBType, Product, LabelVersion, ComplianceCheck, ComplianceRule, CheckResult
    from app.services.llm_service import _ingest_document

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return

    # Remove any existing KB document for this product
    existing = db.query(KBDocument).filter(
        KBDocument.kb_type == KBType.PRODUCTS,
        KBDocument.source.like(f"db:product:{product.id}%"),
    ).all()
    for doc in existing:
        db.query(KBChunk).filter(KBChunk.document_id == doc.id).delete()
        db.delete(doc)
    db.flush()

    # Build content
    latest_lv = (
        db.query(LabelVersion)
        .filter(LabelVersion.product_id == product.id, LabelVersion.is_current == True)
        .first()
    )

    checks_summary = ""
    extraction_text = ""
    if latest_lv:
        checks = (
            db.query(ComplianceCheck)
            .filter(ComplianceCheck.label_version_id == latest_lv.id)
            .all()
        )
        total = len(checks)
        passed = sum(1 for c in checks if c.result == CheckResult.PASS)
        failed = [c for c in checks if c.result == CheckResult.FAIL]

        fail_lines = []
        for fc in failed[:10]:
            rule = db.query(ComplianceRule).filter(ComplianceRule.id == fc.rule_id).first()
            rule_code = rule.rule_code if rule else "Unknown"
            fail_lines.append(f"  - FAIL [{rule_code}]: {fc.message or 'No detail'}")

        score = round((passed / total) * 100) if total else 0
        checks_summary = (
            f"\nLabel Analysis (uploaded {latest_lv.uploaded_at.strftime('%Y-%m-%d')}):\n"
            f"Compliance Score: {score}% ({passed}/{total} checks passed)\n"
            f"Failing Checks:\n"
            + ("\n".join(fail_lines) if fail_lines else "  None")
            + f"\nOCR Text Preview: {(latest_lv.ocr_raw_text or '')[:400]}"
        )

        # Store full extraction data so the LLM learns from every scan
        if latest_lv.extraction_json:
            try:
                extraction_text = (
                    f"\n\nExtracted Label Data (confidence: {latest_lv.extraction_confidence or 0:.0%}):\n"
                    + _json.dumps(latest_lv.extraction_json, indent=2, ensure_ascii=False)[:3000]
                )
            except Exception:
                pass

    content = (
        f"Product: {product.name}\n"
        f"SKU: {product.sku or 'N/A'}\n"
        f"Category: {product.category or 'Nutraceutical'}\n"
        f"Description: {product.description or 'N/A'}\n"
        f"Created: {product.created_at.strftime('%Y-%m-%d')}"
        + checks_summary
        + extraction_text
    )

    _ingest_document(
        db, "products",
        title=f"Product: {product.name}",
        source=f"db:product:{product.id}",
        content=content,
    )


async def _handle_spreadsheet_upload(request: Request, user, file: UploadFile, suffix: str, db: Session):
    """Parse CSV or Excel file as bulk product import."""
    from urllib.parse import quote

    content_bytes = await file.read()
    rows = []

    try:
        if suffix == ".csv":
            text = content_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                rows.append(row)
        elif suffix in (".xlsx", ".xls"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content_bytes), read_only=True, data_only=True)
                ws = wb.active
                headers = [str(c.value or "").strip().lower() for c in next(ws.iter_rows(min_row=1, max_row=1))]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    d = {}
                    for i, val in enumerate(row):
                        if i < len(headers) and headers[i]:
                            d[headers[i]] = str(val).strip() if val is not None else ""
                    if d.get("name"):
                        rows.append(d)
                wb.close()
            except ImportError:
                msg = "Excel support requires openpyxl. Use CSV format instead."
                return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)
    except Exception as e:
        msg = f"Failed to parse file: {str(e)[:100]}"
        return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)

    if not rows:
        msg = "No data rows found in file. Ensure headers include: name, sku, category, description"
        return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)

    VALID_CATS = {
        "health supplement", "nutraceutical", "functional food",
        "food for special dietary use", "novel food", "ayurvedic / asu",
    }

    added = 0
    for row in rows:
        name = row.get("name", "").strip()
        if not name:
            continue
        sku = row.get("sku", "").strip()
        cat = row.get("category", "Health Supplement").strip()
        desc = row.get("description", "").strip()

        if cat.lower() not in VALID_CATS:
            cat = "Health Supplement"

        existing = db.query(Product).filter(
            Product.user_id == user.id,
            Product.name == name,
            Product.is_active == True,
        ).first()
        if existing:
            continue

        p = Product(user_id=user.id, name=name, sku=sku or None, category=cat, description=desc)
        db.add(p)
        added += 1

    db.commit()
    msg = f"Imported {added} product(s) from {file.filename}"
    return RedirectResponse(url=f"/products?msg={quote(msg)}&type=success", status_code=302)


@router.get("/products/bulk-upload")
async def bulk_upload_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    from app.models import Alert, AlertStatus
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("bulk_upload.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "result": None,
    })


@router.post("/products/bulk-upload")
async def bulk_upload_post(
    request: Request,
    csv_data: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    lines = [l.strip() for l in csv_data.strip().splitlines() if l.strip()]
    added, skipped, errors = [], [], []

    # Skip header if present
    if lines and lines[0].lower().startswith("name"):
        lines = lines[1:]

    VALID_CATS = {
        "health supplement", "nutraceutical", "functional food",
        "food for special dietary use", "novel food", "ayurvedic / asu",
    }

    for i, line in enumerate(lines, 1):
        parts = [p.strip().strip('"') for p in line.split(",")]
        if not parts or not parts[0]:
            continue
        name = parts[0]
        sku  = parts[1] if len(parts) > 1 else ""
        cat  = parts[2] if len(parts) > 2 else "Health Supplement"
        desc = parts[3] if len(parts) > 3 else ""

        if cat.lower() not in VALID_CATS:
            cat = "Health Supplement"

        # Skip duplicates
        existing = db.query(Product).filter(
            Product.user_id == user.id,
            Product.name == name,
            Product.is_active == True,
        ).first()
        if existing:
            skipped.append(f"Row {i}: '{name}' already exists")
            continue

        p = Product(user_id=user.id, name=name, sku=sku or None, category=cat, description=desc)
        db.add(p)
        added.append(name)

    db.commit()

    from app.models import Alert, AlertStatus
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("bulk_upload.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "result": {"added": added, "skipped": skipped, "errors": errors},
    })


@router.get("/products/{product_id}")
async def product_detail(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    product = db.query(Product).filter(
        Product.id == product_id, Product.user_id == user.id
    ).first()
    if not product:
        return RedirectResponse(url="/products")

    _ = product.label_versions
    for lv in product.label_versions:
        _ = lv.checks

    return templates.TemplateResponse("product_detail.html", {
        "request": request,
        "user": user,
        "product": product,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/products/{product_id}/delete")
async def delete_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    product = db.query(Product).filter(
        Product.id == product_id, Product.user_id == user.id
    ).first()
    if product:
        product.is_active = False
        db.commit()
    return RedirectResponse(url="/products", status_code=302)
