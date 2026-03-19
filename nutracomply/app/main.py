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
        # v3: RBAC role column
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'account_admin'",
        # v4: team_id for sub-user tracking
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS team_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        # v4: team_invites table
        """CREATE TABLE IF NOT EXISTS team_invites (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'viewer',
            invited_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(100) UNIQUE NOT NULL,
            is_accepted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_team_invites_token ON team_invites (token)",
        "CREATE INDEX IF NOT EXISTS ix_team_invites_email ON team_invites (email)",
        # v5: activity logs
        """CREATE TABLE IF NOT EXISTS activity_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(50),
            resource_id INTEGER,
            detail VARCHAR(500),
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_activity_logs_user_id ON activity_logs (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_activity_logs_action ON activity_logs (action)",
        "CREATE INDEX IF NOT EXISTS ix_activity_logs_created_at ON activity_logs (created_at)",
        # v5: api keys
        """CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            key_prefix VARCHAR(10) NOT NULL,
            key_hash VARCHAR(200) NOT NULL,
            last_used_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys (user_id)",
        # v6: onboarding columns
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_complete BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS company_gstin VARCHAR(20)",
        # v6: product brand column
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS brand VARCHAR(255)",
        # v7: white-label report branding columns
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS report_brand_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS report_brand_color VARCHAR(10)",
        # v8: billing — subscriptions and payment records
        """CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            plan VARCHAR(20) NOT NULL DEFAULT 'free',
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            razorpay_order_id VARCHAR(100),
            razorpay_payment_id VARCHAR(100),
            razorpay_sub_id VARCHAR(100),
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            trial_ends_at TIMESTAMP,
            cancelled_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS payment_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            razorpay_payment_id VARCHAR(100),
            razorpay_order_id VARCHAR(100),
            amount_paise INTEGER NOT NULL,
            currency VARCHAR(5) DEFAULT 'INR',
            plan VARCHAR(20) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'created',
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_payment_records_user_id ON payment_records (user_id)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR(20) DEFAULT 'free'",
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
        from app.models import User, UserRole
        db = SessionLocal()

        # --- ben (regular user) ---
        ben = db.query(User).filter(User.email == "ben").first()
        if not ben:
            ben = User(
                name="Ben",
                email="ben",
                hashed_password=hash_password("admin@123"),
                is_admin=False,
                role=UserRole.ACCOUNT_ADMIN,
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
                role=UserRole.SUPER_ADMIN,
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
from app.routes import renewals as renewals_router
from app.routes import reports as reports_router
from app.routes import checker as checker_router
from app.routes import team as team_router
from app.routes import onboarding as onboarding_router
from app.routes import billing as billing_router

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(labels.router)
app.include_router(alerts.router)
app.include_router(regulations.router)
app.include_router(settings_router.router)
app.include_router(admin.router)
app.include_router(renewals_router.router)
app.include_router(reports_router.router)
app.include_router(checker_router.router)
app.include_router(team_router.router)
app.include_router(onboarding_router.router)
app.include_router(billing_router.router)

try:
    from app.routes import admin_llm
    app.include_router(admin_llm.router)
except Exception as _llm_err:
    print(f"[warning] LLM Studio router failed to load: {_llm_err}")


# ── Core page routes (defined AFTER routers but must survive any router error) ─

@app.get("/")
async def root(request: Request):
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/dashboard")
async def dashboard(request: Request):
    from datetime import datetime
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    from app.models import Product, Alert, AlertStatus, LicenseRenewal, PublishedAlert, PublishedAlertStatus

    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    # Redirect new users to onboarding (skip demo accounts ben/admin)
    if not user.onboarding_complete and user.email not in ("ben", "admin"):
        return RedirectResponse(url="/onboarding")

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

    # Licenses expiring in the next 90 days
    from datetime import timedelta
    cutoff = datetime.utcnow() + timedelta(days=90)
    expiring_licenses = (
        db.query(LicenseRenewal)
        .filter(
            LicenseRenewal.user_id == user.id,
            LicenseRenewal.is_active == True,
            LicenseRenewal.expiry_date <= cutoff,
        )
        .order_by(LicenseRenewal.expiry_date.asc())
        .all()
    )

    # Latest 3 published regulation alerts
    recent_reg_alerts = (
        db.query(PublishedAlert)
        .filter(PublishedAlert.status == PublishedAlertStatus.PUBLISHED)
        .order_by(PublishedAlert.published_at.desc())
        .limit(3)
        .all()
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
        "expiring_licenses": expiring_licenses,
        "recent_reg_alerts": recent_reg_alerts,
    })


@app.get("/reg-alerts")
async def reg_alerts(request: Request):
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    from app.models import Alert, AlertStatus, PublishedAlert, PublishedAlertStatus, PublishedAlertSeverity

    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    severity_filter = request.query_params.get("severity", "")
    q = db.query(PublishedAlert).filter(PublishedAlert.status == PublishedAlertStatus.PUBLISHED)
    if severity_filter:
        try:
            q = q.filter(PublishedAlert.severity == PublishedAlertSeverity(severity_filter))
        except ValueError:
            pass

    alerts_list = q.order_by(PublishedAlert.published_at.desc()).all()

    unread_alerts = (
        db.query(Alert)
        .filter(Alert.status == AlertStatus.UNREAD)
        .count()
    )

    return templates.TemplateResponse("reg_alerts.html", {
        "request": request,
        "user": user,
        "alerts": alerts_list,
        "unread_alerts": unread_alerts,
        "current_severity": severity_filter,
    })


@app.get("/pricing")
async def pricing_page(request: Request):
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    return templates.TemplateResponse("pricing.html", {"request": request, "user": user})


@app.get("/r/{token}")
async def shared_report(token: str, request: Request):
    from datetime import datetime
    from app.database import get_db
    from app.models import ComplianceReport

    db = next(get_db())
    report = db.query(ComplianceReport).filter(
        ComplianceReport.share_token == token
    ).first()

    if not report:
        return templates.TemplateResponse("shared_report_expired.html", {
            "request": request,
            "error": "This report link is invalid or has been revoked."
        })

    if report.share_expires_at and report.share_expires_at < datetime.utcnow():
        return templates.TemplateResponse("shared_report_expired.html", {
            "request": request,
            "error": "This report link has expired. Please request a new link from the account holder."
        })

    _ = report.product

    return templates.TemplateResponse("shared_report.html", {
        "request": request,
        "report": report,
        "product": report.product,
    })
