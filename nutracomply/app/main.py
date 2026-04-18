import json
import time
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse

from app.config import get_settings
from app.database import engine, Base, SessionLocal
from app.logging_config import setup_logging, get_logger

setup_logging()
log = get_logger("regbite")

settings = get_settings()

# Warn if SECRET_KEY is still the default
if settings.secret_key == "change-this-secret":
    import warnings
    warnings.warn(
        "SECRET_KEY is still the default! Set a strong SECRET_KEY env var in production.",
        stacklevel=1,
    )

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
        (_create_tables,           "create_tables"),
        (_run_migrations,          "migrations"),
        (_promote_admin,           "promote_admin"),
        (_seed_initial_data,       "seed_initial_data"),
        (_seed_demo_users,         "seed_demo_users"),
        (_auto_seed_kb_if_empty,   "auto_seed_kb"),
    ]
    for fn, name in tasks:
        try:
            fn()
            log.info("[startup] %s OK", name)
        except Exception as exc:
            log.error("[startup] %s error: %s", name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fire DB initialisation in a background thread and yield immediately so
    # uvicorn starts accepting connections (and Railway health checks pass)
    # within milliseconds.  The background thread runs independently.
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run_all_startup_tasks)

    # Start the in-process daily scheduler (replaces Celery Beat + Redis)
    from app.scheduler import start_scheduler
    start_scheduler()

    log.info("[startup] Server ready — DB initialisation running in background")
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
        log.info("[migrate] SQLite — skipping raw SQL migrations (handled by create_all)")
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
        # v9: in-app notifications
        """CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            message VARCHAR(500),
            ntype VARCHAR(20) DEFAULT 'info',
            is_read BOOLEAN DEFAULT FALSE,
            link VARCHAR(300),
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_notifications_is_read ON notifications (is_read)",
        # v10: Blog tables
        """CREATE TABLE IF NOT EXISTS blog_categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            slug VARCHAR(120) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_blog_categories_slug ON blog_categories (slug)",
        """CREATE TABLE IF NOT EXISTS blog_posts (
            id SERIAL PRIMARY KEY,
            title VARCHAR(300) NOT NULL,
            slug VARCHAR(350) NOT NULL UNIQUE,
            excerpt TEXT,
            content TEXT NOT NULL,
            featured_image VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            is_featured BOOLEAN DEFAULT FALSE,
            category_id INTEGER REFERENCES blog_categories(id) ON DELETE SET NULL,
            author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tags VARCHAR(500),
            meta_title VARCHAR(300),
            meta_description VARCHAR(500),
            views INTEGER DEFAULT 0,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_blog_posts_slug ON blog_posts (slug)",
        "CREATE INDEX IF NOT EXISTS ix_blog_posts_status ON blog_posts (status)",
        "CREATE INDEX IF NOT EXISTS ix_blog_posts_published_at ON blog_posts (published_at)",
        # Normalise role column to lowercase values (Python 3.11+ str-enum name/value fix)
        "UPDATE users SET role = 'account_admin' WHERE role = 'ACCOUNT_ADMIN'",
        "UPDATE users SET role = 'super_admin'   WHERE role = 'SUPER_ADMIN'",
        "UPDATE users SET role = 'editor'        WHERE role = 'EDITOR'",
        "UPDATE users SET role = 'viewer'        WHERE role = 'VIEWER'",
        "UPDATE users SET role = 'consultant'    WHERE role = 'CONSULTANT'",
        # v10: rule versioning (Item 5) — version, framework, regulation_status on compliance_rules
        "ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS version VARCHAR(50)",
        "ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS framework VARCHAR(20)",
        "ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS regulation_status VARCHAR(20) DEFAULT 'EFFECTIVE'",
        # v10: regulation status on regulation_changes (Item 8)
        "ALTER TABLE regulation_changes ADD COLUMN IF NOT EXISTS regulation_status VARCHAR(20) DEFAULT 'EFFECTIVE'",
        # v10: perpetual license flag (March 2026 FSSAI amendment)
        "ALTER TABLE license_renewals ADD COLUMN IF NOT EXISTS is_perpetual BOOLEAN DEFAULT FALSE",
        # v11: Performance indexes
        "CREATE INDEX IF NOT EXISTS ix_products_user_active ON products (user_id, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_labels_product_current ON label_versions (product_id, is_current)",
        "CREATE INDEX IF NOT EXISTS ix_checks_label_version ON compliance_checks (label_version_id)",
        "CREATE INDEX IF NOT EXISTS ix_notifications_user_read ON notifications (user_id, is_read)",
        # v12: LLM Studio KB tables (safety-net — also handled by create_all, but explicit here
        #      to guarantee they exist before any route queries them)
        """CREATE TABLE IF NOT EXISTS kb_documents (
            id SERIAL PRIMARY KEY,
            kb_type VARCHAR(20) NOT NULL,
            title VARCHAR(500) NOT NULL,
            source VARCHAR(500),
            content TEXT NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            uploaded_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_kb_documents_kb_type ON kb_documents (kb_type)",
        """CREATE TABLE IF NOT EXISTS kb_chunks (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
            kb_type VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_kb_type ON kb_chunks (kb_type)",
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_document_id ON kb_chunks (document_id)",
        """CREATE TABLE IF NOT EXISTS kb_conversations (
            id SERIAL PRIMARY KEY,
            kb_type VARCHAR(20) NOT NULL,
            admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            messages JSON DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_kb_conversations_unique ON kb_conversations (kb_type, admin_id)",
        # v13: LabelVersion — extraction provenance columns (model added, DB missed)
        "ALTER TABLE label_versions ADD COLUMN IF NOT EXISTS extraction_source VARCHAR(20)",
        "ALTER TABLE label_versions ADD COLUMN IF NOT EXISTS tokens_input INTEGER",
        "ALTER TABLE label_versions ADD COLUMN IF NOT EXISTS tokens_output INTEGER",
        # v14: KBDocument — content_hash for duplicate upload detection
        "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS ix_kb_documents_content_hash ON kb_documents (content_hash)",
        # v15: API call log table (tracks kb_chat, compliance_format, query_expansion)
        """CREATE TABLE IF NOT EXISTS api_call_logs (
            id SERIAL PRIMARY KEY,
            call_type VARCHAR(30) NOT NULL,
            provider VARCHAR(20) NOT NULL,
            model VARCHAR(100),
            tokens_input INTEGER,
            tokens_output INTEGER,
            cost_usd FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_api_call_logs_call_type ON api_call_logs (call_type)",
        "CREATE INDEX IF NOT EXISTS ix_api_call_logs_created_at ON api_call_logs (created_at)",
        # v16: Store file bytes in DB so previews survive Railway container resets
        "ALTER TABLE label_versions ADD COLUMN IF NOT EXISTS file_data BYTEA",
        # v17: Quick-check flag — ephemeral /checker products excluded from catalog, quotas, KB
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_quick_check BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    for sql in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
            log.info("[migrate] OK: %s", sql[:80])
        except Exception as e:
            log.debug("[migrate] Skipped (%s)", e)
    log.info("[migrate] Column migrations complete")


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
    from app.models import (
        ComplianceRule, Ingredient, RegulationChange, Severity, ChangeType,
        RuleFramework, RegulationStatus
    )
    db = SessionLocal()
    try:
        # Seed compliance rules (insert new, update existing regulation_source for Version VIII)
        rules_path = Path(__file__).parent / "data" / "fssai_rules_seed.json"
        with open(rules_path, encoding="utf-8") as f:
            rules_data = json.load(f)
        existing_rules = {r.rule_code: r for r in db.query(ComplianceRule).all()}
        added = 0
        updated = 0
        for r in rules_data:
            code = r["rule_code"]
            # Extract new versioning fields (not part of original ComplianceRule columns by default)
            version = r.pop("version", None)
            framework_str = r.pop("framework", None)
            reg_status_str = r.pop("regulation_status", None)

            if code not in existing_rules:
                rule = ComplianceRule(**r)
                if version:
                    rule.version = version
                if framework_str:
                    try:
                        rule.framework = RuleFramework(framework_str)
                    except (ValueError, KeyError):
                        pass
                if reg_status_str:
                    try:
                        rule.regulation_status = RegulationStatus(reg_status_str)
                    except (ValueError, KeyError):
                        pass
                db.add(rule)
                added += 1
            else:
                # Update regulation_source if it changed (e.g. Version VIII updates)
                existing = existing_rules[code]
                if r.get("regulation_source") and existing.regulation_source != r["regulation_source"]:
                    existing.regulation_source = r["regulation_source"]
                    updated += 1
                # Backfill versioning fields if not set
                if version and not existing.version:
                    existing.version = version
                if framework_str and not existing.framework:
                    try:
                        existing.framework = RuleFramework(framework_str)
                    except (ValueError, KeyError):
                        pass
                if reg_status_str and not existing.regulation_status:
                    try:
                        existing.regulation_status = RegulationStatus(reg_status_str)
                    except (ValueError, KeyError):
                        pass
        if added or updated:
            db.commit()
            print(f"[seed] Rules: {added} new, {updated} updated")
        elif not existing_rules:
            print("[seed] No compliance rules found — seed file may be empty")

        # Seed ingredients (additive — insert any new ingredients not yet in DB)
        ing_path = Path(__file__).parent / "data" / "ingredients_seed.json"
        with open(ing_path, encoding="utf-8") as f:
            ing_data = json.load(f)
        existing_names = {i.name.lower() for i in db.query(Ingredient.name).all()}
        new_ings = [i for i in ing_data if i["name"].lower() not in existing_names]
        if new_ings:
            for i in new_ings:
                db.add(Ingredient(**i))
            db.commit()
            print(f"[seed] Loaded {len(new_ings)} new ingredients")

        # Seed regulation update history (additive — insert new entries by document_hash)
        updates_path = Path(__file__).parent / "data" / "regulation_updates_seed.json"
        with open(updates_path, encoding="utf-8") as f:
            updates_data = json.load(f)
        existing_hashes = {r.document_hash for r in db.query(RegulationChange.document_hash).all() if r.document_hash}
        new_updates = [u for u in updates_data if u.get("document_hash") not in existing_hashes]
        if new_updates:
            for u in new_updates:
                u = dict(u)  # don't mutate original
                detected = datetime.strptime(u.pop("detected_at"), "%Y-%m-%d")
                eff_str = u.pop("effective_date", None)
                effective = datetime.strptime(eff_str, "%Y-%m-%d") if eff_str else None
                reg_status_str = u.pop("regulation_status", None)
                reg_status = None
                if reg_status_str:
                    try:
                        reg_status = RegulationStatus(reg_status_str)
                    except (ValueError, KeyError):
                        pass
                db.add(RegulationChange(
                    detected_at=detected,
                    effective_date=effective,
                    severity=Severity(u.pop("severity")),
                    change_type=ChangeType(u.pop("change_type")),
                    regulation_status=reg_status,
                    **u,
                ))
            db.commit()
            print(f"[seed] Loaded {len(new_updates)} new regulation updates")
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()


def _seed_demo_users():
    """
    Seed demo accounts for every persona on startup (idempotent — skip if already exist).
    All use password admin@123:
      admin      — super_admin (full platform control)
      ben        — account_admin (manage products & team)
      editor     — editor (upload labels & run checks)
      viewer     — viewer (read-only dashboard)
      consultant — consultant (external audit access)
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

        # --- editor (content editor) ---
        editor = db.query(User).filter(User.email == "editor").first()
        if not editor:
            editor = User(
                name="Editor",
                email="editor",
                hashed_password=hash_password("admin@123"),
                is_admin=False,
                role=UserRole.EDITOR,
                is_active=True,
                notification_emails=[],
            )
            db.add(editor)
            db.commit()
            db.refresh(editor)
            print("[demo] Created user: editor")
            try:
                _seed_demo_products(editor, db)
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        else:
            print("[demo] User editor already exists — skipped")

        # --- viewer (read-only) ---
        viewer = db.query(User).filter(User.email == "viewer").first()
        if not viewer:
            viewer = User(
                name="Viewer",
                email="viewer",
                hashed_password=hash_password("admin@123"),
                is_admin=False,
                role=UserRole.VIEWER,
                is_active=True,
                notification_emails=[],
            )
            db.add(viewer)
            db.commit()
            db.refresh(viewer)
            print("[demo] Created user: viewer")
            try:
                _seed_demo_products(viewer, db)
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        else:
            print("[demo] User viewer already exists — skipped")

        # --- consultant (external auditor) ---
        consultant = db.query(User).filter(User.email == "consultant").first()
        if not consultant:
            consultant = User(
                name="Consultant",
                email="consultant",
                hashed_password=hash_password("admin@123"),
                is_admin=False,
                role=UserRole.CONSULTANT,
                is_active=True,
                notification_emails=[],
            )
            db.add(consultant)
            db.commit()
            db.refresh(consultant)
            print("[demo] Created user: consultant")
            try:
                _seed_demo_products(consultant, db)
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        else:
            print("[demo] User consultant already exists — skipped")

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


def _auto_seed_kb_if_empty():
    """
    On every startup: if the Regulations KB has zero documents, auto-seed
    from DB (compliance rules + ingredients + regulation changes).

    This handles the 'clear KB → redeploy → fresh' workflow automatically
    so admins don't have to click 'Auto-Seed from DB' manually.

    Safe to run repeatedly — seed_regulations_kb is fully additive
    (skips sources that already exist).
    """
    from app.models import KBDocument, KBType
    from app.services.llm_service import seed_regulations_kb
    db = SessionLocal()
    try:
        count = db.query(KBDocument).filter(
            KBDocument.kb_type == KBType.REGULATIONS,
            KBDocument.is_active,
        ).count()
        if count == 0:
            result = seed_regulations_kb(db)
            seeded = result.get("document_count", 0)
            log.info("[startup] Regulations KB was empty — auto-seeded %d documents", seeded)
        else:
            log.info("[startup] Regulations KB already has %d documents — skipping auto-seed", count)
    except Exception as exc:
        log.error("[startup] auto_seed_kb error: %s", exc)
    finally:
        db.close()


app = FastAPI(title="RegBite", lifespan=lifespan)

# Request logging middleware
from starlette.middleware.base import BaseHTTPMiddleware

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000)
        # Skip static/upload paths for less noise
        path = request.url.path
        if not path.startswith(("/static/", "/uploads/")):
            log.info(
                "%s %s %s %dms",
                request.method, path, response.status_code, duration_ms,
                extra={
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "ip": request.client.host if request.client else None,
                },
            )
        return response

app.add_middleware(RequestLoggingMiddleware)

# CSRF protection
from app.services.csrf import CSRFMiddleware, COOKIE_NAME as CSRF_COOKIE, generate_csrf_token
app.add_middleware(CSRFMiddleware)

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve uploaded label files (images/PDFs)
uploads_dir = Path(settings.upload_dir)
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Make csrf_token() available in all templates
def _csrf_input(request: Request) -> str:
    """Return an HTML hidden input with the CSRF token."""
    token = request.cookies.get(CSRF_COOKIE, generate_csrf_token())
    return f'<input type="hidden" name="csrf_token" value="{token}">'

templates.env.globals["csrf_input"] = _csrf_input

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
from app.routes import notifications as notifications_router
from app.routes import help as help_router
from app.routes import blog as blog_router

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
app.include_router(notifications_router.router)
app.include_router(help_router.router)
app.include_router(blog_router.router)

try:
    from app.routes import admin_llm
    app.include_router(admin_llm.router)
except Exception as _llm_err:
    log.warning("[warning] LLM Studio router failed to load: %s", _llm_err)


# ── Exception handlers ─────────────────────────────────────────────────────────

from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return templates.TemplateResponse("500.html", {"request": request}, status_code=exc.status_code)


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Railway healthcheck — verifies DB connectivity."""
    from sqlalchemy import text
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return JSONResponse({"status": "ok"})
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)


# ── Core page routes (defined AFTER routers but must survive any router error) ─

@app.get("/")
async def root(request: Request):
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    try:
        db = next(get_db())
        user = get_current_user_from_cookie(request, db)
    except Exception as e:
        print(f"[root] DB not ready: {e}")
        user = None
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/dashboard")
async def dashboard(request: Request):
    from datetime import datetime
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    from app.models import Product, Alert, AlertStatus, LabelVersion, LicenseRenewal, PublishedAlert, PublishedAlertStatus, Notification
    from sqlalchemy.orm import selectinload

    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    # Redirect new users to onboarding (skip demo accounts ben/admin)
    if not user.onboarding_complete and user.email not in ("ben", "admin"):
        return RedirectResponse(url="/onboarding")

    # Eager-load label_versions→checks in 2 queries instead of N+1
    products_list = (
        db.query(Product)
        .options(
            selectinload(Product.label_versions)
            .selectinload(LabelVersion.checks)
        )
        .filter(Product.user_id == user.id, Product.is_active == True)
        .all()
    )

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

    unread_notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read == False)
        .count()
    )

    # Scan usage this month
    from datetime import timedelta
    from app.services.quota_service import get_user_plan
    from app.services.billing_service import PLANS
    now_dt = datetime.utcnow()
    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    scans_this_month = (
        db.query(LabelVersion)
        .join(Product, LabelVersion.product_id == Product.id)
        .filter(Product.user_id == user.id, LabelVersion.uploaded_at >= month_start)
        .count()
    )
    plan_key = get_user_plan(user, db)
    plan_limits = PLANS.get(plan_key, PLANS["free"])
    scan_limit = plan_limits.get("scan_limit_monthly")

    # Licenses expiring in the next 90 days
    cutoff = datetime.utcnow() + timedelta(days=90)
    expiring_licenses = (
        db.query(LicenseRenewal)
        .filter(
            LicenseRenewal.user_id == user.id,
            LicenseRenewal.is_active == True,
            LicenseRenewal.expiry_date <= cutoff,
        )
        .order_by(LicenseRenewal.expiry_date.asc())
        .limit(2)
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
        "unread_notifications": unread_notifications,
        "total_products": total_products,
        "compliant_count": len(compliant_list),
        "flagged_count": len(flagged_list),
        "no_label_count": len(no_label_list),
        "categories": dict(categories),
        "expiring_licenses": expiring_licenses,
        "recent_reg_alerts": recent_reg_alerts,
        "now": datetime.utcnow(),
        "scans_this_month": scans_this_month,
        "scan_limit": scan_limit,
        "plan_name": plan_limits.get("name", "Starter"),
    })


@app.get("/reg-alerts")
async def reg_alerts(request: Request):
    """Redirect legacy /reg-alerts to /regulations?tab=notices."""
    severity = request.query_params.get("severity", "")
    url = "/regulations?tab=notices"
    if severity:
        url += f"&notice_severity={severity}"
    return RedirectResponse(url=url, status_code=301)


@app.get("/pricing")
async def pricing_page(request: Request):
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    return templates.TemplateResponse("pricing.html", {"request": request, "user": user})


def _get_optional_user(request: Request):
    """Return current user or None (never raises)."""
    from app.routes.auth import get_current_user_from_cookie
    from app.database import get_db
    try:
        db = next(get_db())
        return get_current_user_from_cookie(request, db)
    except Exception:
        return None


@app.get("/features")
async def features_page(request: Request):
    return templates.TemplateResponse("features.html", {"request": request, "user": _get_optional_user(request), "active_page": "features"})


@app.get("/about")
async def about_page(request: Request):
    return templates.TemplateResponse("about.html", {"request": request, "user": _get_optional_user(request), "active_page": "about"})


@app.get("/contact")
async def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {
        "request": request, "user": _get_optional_user(request), "active_page": "contact",
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "success"),
    })


@app.post("/contact/submit")
async def contact_submit(request: Request):
    form = await request.form()
    name = form.get("name", "")
    email = form.get("email", "")
    message = form.get("message", "")
    inquiry_type = form.get("inquiry_type", "other")
    company = form.get("company", "")
    # Log the contact submission (in production, send email via Brevo)
    print(f"[contact] {inquiry_type} from {name} <{email}> ({company}): {message[:200]}")
    from urllib.parse import quote
    return RedirectResponse(
        url=f"/contact?msg={quote('Message sent! We will get back to you within 24 hours.')}&type=success",
        status_code=302,
    )


@app.get("/help")
async def help_page(request: Request):
    return templates.TemplateResponse("help.html", {"request": request, "user": _get_optional_user(request), "active_page": "help"})


@app.get("/terms")
async def terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request, "user": _get_optional_user(request), "active_page": "terms"})


@app.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request, "user": _get_optional_user(request), "active_page": "privacy"})


@app.get("/changelog")
async def changelog_page(request: Request):
    return templates.TemplateResponse("changelog.html", {"request": request, "user": _get_optional_user(request), "active_page": "changelog"})


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
