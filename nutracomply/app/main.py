import os
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.database import engine, Base, SessionLocal

settings = get_settings()

# Ensure upload directory exists
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all DB tables
    Base.metadata.create_all(bind=engine)
    # Run column migrations for tables that already existed before model changes
    _run_migrations()
    # Seed rules and ingredients on first run
    _seed_initial_data()
    yield


def _run_migrations():
    """
    Add new columns to existing tables that were created before model changes.
    Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS — safe to run on every startup.
    """
    migrations = [
        # Added in v2: admin flag + per-user notification emails
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_emails JSON DEFAULT '[]'",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__('sqlalchemy').text(sql))
            except Exception as e:
                print(f"[migrate] Warning: {e}")
        conn.commit()
    print("[migrate] Column migrations applied")


def _seed_initial_data():
    from datetime import datetime
    from app.models import ComplianceRule, Ingredient, RegulationChange, Severity, ChangeType
    db = SessionLocal()
    try:
        # Seed compliance rules
        if db.query(ComplianceRule).count() == 0:
            rules_path = Path(__file__).parent / "data" / "fssai_rules_seed.json"
            with open(rules_path, encoding="utf-8") as f:
                rules_data = json.load(f)
            for r in rules_data:
                db.add(ComplianceRule(**r))
            db.commit()
            print(f"[seed] Loaded {len(rules_data)} FSSAI compliance rules")

        # Seed ingredients
        if db.query(Ingredient).count() == 0:
            ing_path = Path(__file__).parent / "data" / "ingredients_seed.json"
            with open(ing_path, encoding="utf-8") as f:
                ing_data = json.load(f)
            for i in ing_data:
                db.add(Ingredient(**i))
            db.commit()
            print(f"[seed] Loaded {len(ing_data)} ingredients")

        # Seed regulation update history
        if db.query(RegulationChange).count() == 0:
            updates_path = Path(__file__).parent / "data" / "regulation_updates_seed.json"
            with open(updates_path, encoding="utf-8") as f:
                updates_data = json.load(f)
            for u in updates_data:
                # Parse date strings
                detected = datetime.strptime(u.pop("detected_at"), "%Y-%m-%d")
                eff_str = u.pop("effective_date", None)
                effective = datetime.strptime(eff_str, "%Y-%m-%d") if eff_str else None
                db.add(RegulationChange(
                    detected_at=detected,
                    effective_date=effective,
                    severity=Severity(u.pop("severity")),
                    change_type=ChangeType(u.pop("change_type")),
                    **u,
                ))
            db.commit()
            print(f"[seed] Loaded {len(updates_data)} regulation updates")
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()


app = FastAPI(title="RegBite", lifespan=lifespan)

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Register routers
from app.routes import auth, products, labels, alerts, regulations, settings, admin

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(labels.router)
app.include_router(alerts.router)
app.include_router(regulations.router)
app.include_router(settings.router)
app.include_router(admin.router)


@app.get("/")
async def root(request: Request):
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
async def dashboard(request: Request):
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    from app.models import Product, Alert, AlertStatus

    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    products_list = (
        db.query(Product)
        .filter(Product.user_id == user.id, Product.is_active == True)
        .all()
    )

    # Force load label_versions and checks (avoids lazy-load issues)
    for p in products_list:
        _ = p.label_versions
        for lv in p.label_versions:
            _ = lv.checks

    # Summary stats
    total_products  = len(products_list)
    compliant_list  = [p for p in products_list if p.compliance_score is not None and p.compliance_score >= 80]
    flagged_list    = [p for p in products_list if p.compliance_score is not None and p.compliance_score < 80]
    no_label_list   = [p for p in products_list if p.compliance_score is None]

    # Category breakdown
    categories: dict = defaultdict(list)
    for p in products_list:
        cat = p.category or "Nutraceutical"
        categories[cat].append(p)

    unread_alerts = (
        db.query(Alert)
        .filter(Alert.status == AlertStatus.UNREAD)
        .count()
    )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "products": products_list,
        "unread_alerts": unread_alerts,
        "total_products": total_products,
        "compliant_count": len(compliant_list),
        "flagged_count": len(flagged_list),
        "no_label_count": len(no_label_list),
        "categories": dict(categories),
    })
