import os
import json
import asyncio
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


def _create_tables():
    """Create all tables (idempotent)."""
    Base.metadata.create_all(bind=engine)



def _run_all_startup_tasks():
    """
    Run all DB initialisation tasks sequentially in a background thread.
    Errors in individual steps are caught and logged so a failure in one
    step never prevents the remaining steps from running.
    """
    tasks = [
        (_create_tables,     "create_tables"),
        (_run_migrations,    "migrations"),
        (_promote_admin,     "promote_admin"),
        (_seed_initial_data, "seed_initial_data"),
        (_seed_demo_users,   "seed_demo_users"),
    ]
    for fn, name in tasks:
        try:
            fn()
            print(f"[startup] {name} OK")
        except Exception as exc:
            print(f"[startup] {name} error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fire DB initialisation in a background thread and yield immediately so
    # uvicorn starts accepting connections (and Railway health checks pass)
    # within milliseconds.  The background thread runs independently.
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run_all_startup_tasks)
    print("[startup] Server ready — DB initialisation running in background")
    yield


def _run_migrations():
    """
    Add new columns to existing tables that were created before model changes.

    SQLite notes:
    - SQLite does NOT support ALTER TABLE … IF NOT EXISTS or SERIAL/NOW().
    - For SQLite we skip the raw ALTER TABLE statements entirely because
      _create_tables() (Base.metadata.create_all) already creates every table
      with all current columns on a fresh database.
    - The v3 LLM tables are also skipped here for both backends because
      Base.metadata.create_all handles them cleanly (it checks existence first).
    - Only the v2 ALTER TABLE statements are needed, and only on PostgreSQL
      (for databases that existed before the is_admin column was added).
    """
    from sqlalchemy import text

    _sqlite = settings.database_url.startswith("sqlite")
    if _sqlite:
        print("[migrate] SQLite — skipping raw SQL migrations (handled by create_all)")
        return

    # PostgreSQL only: add columns that may be missing from pre-v2 databases.
    # CREATE TABLE statements for v3 (LLM Studio) are intentionally omitted here;
    # Base.metadata.create_all already created them above.
    migrations = [
        # v2: admin flag + per-user notification emails
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_emails JSON DEFAULT '[]'",
    ]
    for sql in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
            print(f"[migrate] OK: {sql}")
        except Exception as e:
            print(f"[migrate] Skipped ({e})")
    print("[migrate] Column migrations complete")


def _promote_admin():
    """
    On every startup: if ADMIN_EMAIL is set in config, find that user in the DB
    and ensure is_admin=True. This handles both new registrations and existing
    accounts that pre-date the is_admin column.
    """
    if not settings.admin_email:
        return
    from app.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(
            User.email == settings.admin_email.lower().strip()
        ).first()
        if user and not user.is_admin:
            user.is_admin = True
            db.commit()
            print(f"[admin] Promoted {user.email} to super admin")
        elif user:
            print(f"[admin] {user.email} is already super admin")
        else:
            print(f"[admin] ADMIN_EMAIL={settings.admin_email} — user not found yet (will be promoted on registration)")
    except Exception as e:
        db.rollback()
        print(f"[admin] Promotion error: {e}")
    finally:
        db.close()


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


def _seed_demo_users():
    """
    Seed two hardcoded demo accounts on every startup (idempotent — skip if already exist).
      ben   / admin@123  — regular user, gets 5 demo products
      admin / admin@123  — super admin
    """
    db = None
    try:
        from app.routes.auth import hash_password, _seed_demo_products
        from app.models import User
        db = SessionLocal()

        # --- ben (regular user) ---
        ben = db.query(User).filter(User.email == "ben").first()
        if not ben:
            ben = User(
                name="Ben",
                email="ben",
                hashed_password=hash_password("admin@123"),
                is_admin=False,
                is_active=True,
                notification_emails=[],
            )
            db.add(ben)
            db.commit()
            db.refresh(ben)
            print("[demo] Created user: ben")
            try:
                _seed_demo_products(ben, db)
                print("[demo] Seeded demo products for ben")
            except Exception as e:
                print(f"[demo] Product seed failed: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
        else:
            print("[demo] User ben already exists — skipped")

        # --- admin (super admin) ---
        adm = db.query(User).filter(User.email == "admin").first()
        if not adm:
            adm = User(
                name="Admin",
                email="admin",
                hashed_password=hash_password("admin@123"),
                is_admin=True,
                is_active=True,
                notification_emails=[],
            )
            db.add(adm)
            db.commit()
            print("[demo] Created user: admin")
        else:
            if not adm.is_admin:
                adm.is_admin = True
                db.commit()
            print("[demo] User admin already exists — skipped")

    except Exception as e:
        print(f"[demo] User seed error: {e}")
        if db:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


app = FastAPI(title="RegBite", lifespan=lifespan)

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Register routers
# NOTE: import settings route as settings_router to avoid shadowing the
# module-level `settings = get_settings()` config object.
from app.routes import auth, products, labels, alerts, regulations, admin
from app.routes import settings as settings_router

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(labels.router)
app.include_router(alerts.router)
app.include_router(regulations.router)
app.include_router(settings_router.router)
app.include_router(admin.router)

try:
    from app.routes import admin_llm
    app.include_router(admin_llm.router)
except Exception as _llm_err:
    print(f"[warning] LLM Studio router failed to load: {_llm_err}")


# ── Core page routes (defined AFTER routers but must survive any router error) ─

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
