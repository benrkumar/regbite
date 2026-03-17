from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import Product, LabelVersion
from app.routes.auth import get_current_user_from_cookie

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


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
    })


@router.post("/products/add")
async def add_product(
    request: Request,
    name: str = Form(...),
    sku: str = Form(""),
    category: str = Form("Health Supplement"),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    product = Product(
        user_id=user.id,
        name=name,
        sku=sku or None,
        category=category,
        description=description,
    )
    db.add(product)
    db.commit()
    return RedirectResponse(url=f"/products/{product.id}", status_code=302)


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
        "food for special dietary use", "novel food",
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
