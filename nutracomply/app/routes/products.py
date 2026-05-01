from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Product, LabelVersion
from app.routes.auth import get_current_user_from_cookie
from app.routes.labels import _prime_label_processing, _process_label_balanced
from app.services.access_control import can_mutate_products, get_account_id
from app.services.alert_service import count_unread_alerts
from app.services.activity_service import log_action
from app.services.billing_service import PLANS
from app.services.quota_service import check_product_limit, check_scan_limit, get_user_plan
from app.services.scan_eta_service import format_eta_window
from app.services.upload_service import (
    ALLOWED_LABEL_EXTENSIONS,
    persist_upload_bytes,
    validate_upload_content,
)

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SPREADSHEET_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def require_user(request: Request, db: Session):
    return get_current_user_from_cookie(request, db)


def _product_query(db: Session, user, *, include_inactive: bool = False, include_temporary: bool = False):
    account_id = get_account_id(user)
    query = db.query(Product)
    if account_id:
        query = query.filter(Product.account_id == account_id)
    else:
        query = query.filter(Product.user_id == user.id)
    if not include_inactive:
        query = query.filter(Product.is_active == True)
    if not include_temporary:
        query = query.filter(Product.is_temporary == False)
    return query


def _remaining_product_slots(user, db) -> int | None:
    plan_key = get_user_plan(user, db)
    max_products = PLANS.get(plan_key, PLANS["free"]).get("product_limit")
    if max_products is None:
        return None
    current_count = (
        _product_query(db, user, include_temporary=False)
        .filter(Product.is_sample == False)
        .count()
    )
    return max(max_products - current_count, 0)


@router.get("/products")
async def products_list(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    products = (
        _product_query(db, user)
        .order_by(Product.created_at.desc())
        .all()
    )
    for product in products:
        _ = product.label_versions
        for label_version in product.label_versions:
            _ = label_version.checks

    archived_count = _product_query(db, user, include_inactive=True).filter(Product.is_active == False, Product.is_temporary == False).count()

    return templates.TemplateResponse("products.html", {
        "request": request,
        "user": user,
        "products": products,
        "archived_count": archived_count,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
        "can_mutate_products": can_mutate_products(user),
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
    from urllib.parse import quote

    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_mutate_products(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    if file and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix in SPREADSHEET_EXTENSIONS:
            return await _handle_spreadsheet_upload(request, user, file, suffix, db)
        if suffix not in ALLOWED_LABEL_EXTENSIONS:
            from urllib.parse import quote
            msg = f"Unsupported file type '{suffix}'. Use image/PDF for labels or CSV/Excel for bulk import."
            return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)

    allowed, quota_msg = check_product_limit(user, db)
    if not allowed:
        from urllib.parse import quote
        return RedirectResponse(url=f"/products?msg={quote(quota_msg)}&type=error", status_code=302)

    product = Product(
        account_id=get_account_id(user),
        user_id=user.id,
        name=name.strip(),
        sku=sku or None,
        category=category,
        description=description,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    log_action(
        user.id,
        "product_created",
        "product",
        product.id,
        detail=f"Created product {product.name}",
        request=request,
        context={"category": product.category, "sku": product.sku},
    )

    if file and file.filename:
        allowed_scan, quota_msg = check_scan_limit(user, db)
        if not allowed_scan:
            product.is_active = False
            db.commit()
            return RedirectResponse(url=f"/products?msg={quote(quota_msg)}&type=error", status_code=302)
        label_version = await _save_label_file(file, product, db)
        _prime_label_processing(label_version, db)
        background_tasks.add_task(_process_label_balanced, label_version.id)
        log_action(
            user.id,
            "label_uploaded",
            "label",
            label_version.id,
            detail=f"Uploaded label for {product.name}",
            request=request,
            context={"product_id": product.id, "file_name": file.filename},
        )
        eta_text = format_eta_window([label_version.file_type or "image"])
        msg = (
            f"Queued background analysis for {product.name}. Go to Products - "
            f"we'll notify you when the label is ready. Estimated {eta_text}."
        )
        return RedirectResponse(url=f"/products?msg={quote(msg)}&type=success", status_code=302)

    return RedirectResponse(url=f"/products/{product.id}", status_code=302)


async def _save_label_file(file: UploadFile, product: Product, db: Session) -> LabelVersion:
    content = await file.read()
    suffix = validate_upload_content(file.filename or "", content)
    file_path = persist_upload_bytes(settings.upload_dir, str(product.id), suffix, content)

    db.query(LabelVersion).filter(
        LabelVersion.product_id == product.id,
        LabelVersion.is_current == True,
    ).update({"is_current": False})

    label_version = LabelVersion(
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
    db.add(label_version)
    db.commit()
    db.refresh(label_version)
    return label_version


def _feed_product_to_llm(product_id: int, db):
    import json as _json

    from app.models import KBDocument, KBChunk, KBType, Product, LabelVersion, ComplianceCheck, ComplianceRule, CheckResult
    from app.services.llm_service import _ingest_document

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or product.is_temporary or product.is_sample:
        return

    existing = db.query(KBDocument).filter(
        KBDocument.kb_type == KBType.PRODUCTS,
        KBDocument.source.like(f"db:product:{product.id}%"),
    ).all()
    for document in existing:
        db.query(KBChunk).filter(KBChunk.document_id == document.id).delete()
        db.delete(document)
    db.flush()

    latest_lv = db.query(LabelVersion).filter(LabelVersion.product_id == product.id, LabelVersion.is_current == True).first()
    checks_summary = ""
    extraction_text = ""
    if latest_lv:
        checks = db.query(ComplianceCheck).filter(ComplianceCheck.label_version_id == latest_lv.id).all()
        total = len(checks)
        passed = sum(1 for check in checks if check.result == CheckResult.PASS)
        failed = [check for check in checks if check.result == CheckResult.FAIL]
        fail_lines = []
        for failed_check in failed[:10]:
            rule = db.query(ComplianceRule).filter(ComplianceRule.id == failed_check.rule_id).first()
            rule_code = rule.rule_code if rule else "Unknown"
            fail_lines.append(f"  - FAIL [{rule_code}]: {failed_check.message or 'No detail'}")

        from app.services.compliance_engine import calculate_compliance_score as calc_score

        score = calc_score(checks)
        checks_summary = (
            f"\nLabel Analysis (uploaded {latest_lv.uploaded_at.strftime('%Y-%m-%d')}):\n"
            f"Compliance Score: {score}% ({passed}/{total} checks passed, severity-weighted)\n"
            f"Failing Checks:\n"
            + ("\n".join(fail_lines) if fail_lines else "  None")
            + f"\nOCR Text Preview: {(latest_lv.ocr_raw_text or '')[:400]}"
        )
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
        db,
        "products",
        title=f"Product: {product.name}",
        source=f"db:product:{product.id}",
        content=content,
        account_id=product.account_id,
    )


async def _handle_spreadsheet_upload(request: Request, user, file: UploadFile, suffix: str, db: Session):
    from urllib.parse import quote

    content_bytes = await file.read()
    rows = []

    try:
        if suffix == ".csv":
            text = content_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows.extend(reader)
        elif suffix in (".xlsx", ".xls"):
            try:
                import openpyxl
                workbook = openpyxl.load_workbook(io.BytesIO(content_bytes), read_only=True, data_only=True)
                worksheet = workbook.active
                headers = [str(cell.value or "").strip().lower() for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
                for row in worksheet.iter_rows(min_row=2, values_only=True):
                    record = {}
                    for index, value in enumerate(row):
                        if index < len(headers) and headers[index]:
                            record[headers[index]] = str(value).strip() if value is not None else ""
                    if record.get("name"):
                        rows.append(record)
                workbook.close()
            except ImportError:
                msg = "Excel support requires openpyxl. Use CSV format instead."
                return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)
    except Exception as exc:
        msg = f"Failed to parse file: {str(exc)[:100]}"
        return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)

    if not rows:
        msg = "No data rows found in file. Ensure headers include: name, sku, category, description"
        return RedirectResponse(url=f"/products?msg={quote(msg)}&type=error", status_code=302)

    remaining_slots = _remaining_product_slots(user, db)
    valid_categories = {
        "health supplement", "nutraceutical", "functional food",
        "food for special dietary use", "novel food", "ayurvedic / asu",
    }

    added = 0
    for row in rows:
        if remaining_slots is not None and remaining_slots <= 0:
            break
        name = row.get("name", "").strip()
        if not name:
            continue
        sku = row.get("sku", "").strip()
        category = row.get("category", "Health Supplement").strip()
        description = row.get("description", "").strip()
        if category.lower() not in valid_categories:
            category = "Health Supplement"

        existing = _product_query(db, user).filter(Product.name == name).first()
        if existing:
            continue

        db.add(Product(
            account_id=get_account_id(user),
            user_id=user.id,
            name=name,
            sku=sku or None,
            category=category,
            description=description,
        ))
        added += 1
        if remaining_slots is not None:
            remaining_slots -= 1

    db.commit()
    if added:
        log_action(
            user.id,
            "product_bulk_imported",
            "product",
            detail=f"Imported {added} products from {file.filename}",
            request=request,
            context={"added": added, "source_file": file.filename, "rows_seen": len(rows)},
        )
    msg = f"Imported {added} product(s) from {file.filename}"
    if remaining_slots == 0 and added < len(rows):
        msg += ". Workspace product limit reached; some rows were skipped."
    return RedirectResponse(url=f"/products?msg={quote(msg)}&type=success", status_code=302)


@router.get("/products/bulk-upload")
async def bulk_upload_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("bulk_upload.html", {
        "request": request,
        "user": user,
        "unread_alerts": count_unread_alerts(db, user),
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
        "result": None,
        "can_mutate_products": can_mutate_products(user),
    })


@router.post("/products/bulk-upload")
async def bulk_upload_post(request: Request, csv_data: str = Form(...), db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_mutate_products(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    lines = [line.strip() for line in csv_data.strip().splitlines() if line.strip()]
    if lines and lines[0].lower().startswith("name"):
        lines = lines[1:]

    added, skipped, errors = [], [], []
    remaining_slots = _remaining_product_slots(user, db)
    valid_categories = {
        "health supplement", "nutraceutical", "functional food",
        "food for special dietary use", "novel food", "ayurvedic / asu",
    }

    for index, line in enumerate(lines, 1):
        if remaining_slots is not None and remaining_slots <= 0:
            skipped.append(f"Row {index}: workspace product limit reached")
            continue

        parts = [part.strip().strip('"') for part in line.split(",")]
        if not parts or not parts[0]:
            continue
        name = parts[0]
        sku = parts[1] if len(parts) > 1 else ""
        category = parts[2] if len(parts) > 2 else "Health Supplement"
        description = parts[3] if len(parts) > 3 else ""
        if category.lower() not in valid_categories:
            category = "Health Supplement"

        existing = _product_query(db, user).filter(Product.name == name).first()
        if existing:
            skipped.append(f"Row {index}: '{name}' already exists")
            continue

        db.add(Product(
            account_id=get_account_id(user),
            user_id=user.id,
            name=name,
            sku=sku or None,
            category=category,
            description=description,
        ))
        added.append(name)
        if remaining_slots is not None:
            remaining_slots -= 1

    db.commit()
    if added or skipped:
        log_action(
            user.id,
            "product_bulk_imported",
            "product",
            detail=f"Bulk pasted {len(added)} products with {len(skipped)} skipped",
            request=request,
            context={"added": len(added), "skipped": len(skipped), "errors": len(errors)},
        )
    return templates.TemplateResponse("bulk_upload.html", {
        "request": request,
        "user": user,
        "unread_alerts": count_unread_alerts(db, user),
        "result": {"added": added, "skipped": skipped, "errors": errors},
        "can_mutate_products": can_mutate_products(user),
    })


@router.post("/products/bulk-upload-files")
async def bulk_upload_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_mutate_products(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    added, skipped, errors = [], [], []
    queued_file_types = []
    remaining_slots = _remaining_product_slots(user, db)

    for upload in files:
        if not upload.filename:
            continue
        if remaining_slots is not None and remaining_slots <= 0:
            skipped.append(f"'{upload.filename}' - workspace product limit reached")
            continue

        suffix = Path(upload.filename).suffix.lower()
        if suffix not in ALLOWED_LABEL_EXTENSIONS:
            errors.append(f"'{upload.filename}' - unsupported file type")
            continue

        product_name = Path(upload.filename).stem.replace("_", " ").replace("-", " ").strip() or f"Product {uuid.uuid4().hex[:6]}"
        existing = _product_query(db, user).filter(Product.name == product_name).first()
        if existing:
            skipped.append(f"'{upload.filename}' - product '{product_name}' already exists")
            continue

        allowed_scan, quota_msg = check_scan_limit(user, db)
        if not allowed_scan:
            errors.append(quota_msg)
            break

        try:
            product = Product(
                account_id=get_account_id(user),
                user_id=user.id,
                name=product_name,
                category="Health Supplement",
            )
            db.add(product)
            db.commit()
            db.refresh(product)

            label_version = await _save_label_file(upload, product, db)
            _prime_label_processing(label_version, db)
            background_tasks.add_task(_process_label_balanced, label_version.id)
            queued_file_types.append(label_version.file_type or ("pdf" if suffix == ".pdf" else "image"))
            log_action(
                user.id,
                "product_created",
                "product",
                product.id,
                detail=f"Created product {product.name} from bulk label upload",
                request=request,
                context={"source_file": upload.filename},
            )
            log_action(
                user.id,
                "label_uploaded",
                "label",
                label_version.id,
                detail=f"Queued bulk label upload for {product.name}",
                request=request,
                context={"product_id": product.id, "file_name": upload.filename},
            )
            added.append(product_name)
            if remaining_slots is not None:
                remaining_slots -= 1
        except Exception as exc:
            errors.append(f"'{upload.filename}' - {exc}")

    if added or skipped or errors:
        log_action(
            user.id,
            "product_bulk_imported",
            "product",
            detail=f"Bulk file upload queued {len(added)} labels with {len(skipped)} skipped and {len(errors)} errors",
            request=request,
            context={"added": len(added), "skipped": len(skipped), "errors": len(errors)},
        )

    if added:
        eta_text = format_eta_window(queued_file_types, default_count=len(added))
        msg = (
            f"Queued {len(added)} label scan{'s' if len(added) != 1 else ''} in the background. "
            f"Go to Products - we'll notify you when analysis is done. Estimated {eta_text}."
        )
        details = []
        if skipped:
            details.append(f"{len(skipped)} skipped")
        if errors:
            details.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
        if details:
            msg += " " + ", ".join(details) + "."
        return RedirectResponse(url=f"/products?msg={quote(msg)}&type=success", status_code=302)

    msg = "No label scans were queued."
    if errors:
        msg += f" {errors[0]}"
    elif skipped:
        msg += f" {skipped[0]}"
    return RedirectResponse(url=f"/products/bulk-upload?msg={quote(msg)}&type=error", status_code=302)


@router.get("/products/archived")
async def archived_products(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    products = (
        _product_query(db, user, include_inactive=True)
        .filter(Product.is_active == False)
        .order_by(Product.updated_at.desc())
        .all()
    )
    for product in products:
        _ = product.label_versions

    return templates.TemplateResponse("products_archived.html", {
        "request": request,
        "user": user,
        "products": products,
        "archived_count": len(products),
    })


@router.get("/products/{product_id}")
async def product_detail(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    product = _product_query(db, user, include_inactive=True).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse(url="/products")

    _ = product.label_versions
    for label_version in product.label_versions:
        _ = label_version.checks

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
        return RedirectResponse(url="/login", status_code=302)
    if not can_mutate_products(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    product = _product_query(db, user, include_inactive=True).filter(Product.id == product_id).first()
    if product:
        product.is_active = False
        db.commit()
        log_action(
            user.id,
            "product_deleted",
            "product",
            product.id,
            detail=f"Removed product {product.name}",
            request=request,
        )
    return RedirectResponse(url="/products", status_code=302)


@router.post("/products/{product_id}/archive")
async def archive_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_mutate_products(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    product = _product_query(db, user, include_inactive=True).filter(Product.id == product_id).first()
    if product:
        product.is_active = False
        db.commit()
        log_action(
            user.id,
            "product_archived",
            "product",
            product.id,
            detail=f"Archived product {product.name}",
            request=request,
        )
    return RedirectResponse(url="/products", status_code=302)


@router.post("/products/{product_id}/restore")
async def restore_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not can_mutate_products(user):
        return RedirectResponse(url="/products?msg=Read-only+role&type=error", status_code=302)

    product = _product_query(db, user, include_inactive=True).filter(Product.id == product_id).first()
    if product:
        product.is_active = True
        db.commit()
        log_action(
            user.id,
            "product_restored",
            "product",
            product.id,
            detail=f"Restored product {product.name}",
            request=request,
        )
    return RedirectResponse(url="/products/archived", status_code=302)


@router.post("/products/bulk-action")
async def bulk_action(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse as _JSONResponse

    user = require_user(request, db)
    if not user:
        return _JSONResponse({"error": "Not authenticated"}, status_code=401)
    if not can_mutate_products(user):
        return _JSONResponse({"error": "Read-only role"}, status_code=403)

    data = await request.json()
    action = data.get("action")
    ids = data.get("ids", [])
    if not ids or action not in ("archive", "delete"):
        return _JSONResponse({"error": "Invalid request"}, status_code=400)

    products = _product_query(db, user, include_inactive=True).filter(Product.id.in_(ids)).all()
    count = 0
    for product in products:
        product.is_active = False
        count += 1

    db.commit()
    return _JSONResponse({"success": True, "count": count})
