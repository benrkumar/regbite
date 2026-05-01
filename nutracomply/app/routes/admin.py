"""
Super Admin Panel Routes
All routes require is_admin=True on the current user.
Admin is designated by matching ADMIN_EMAIL env var on registration.
"""
from datetime import datetime
from urllib.parse import quote_plus
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from pathlib import Path

from sqlalchemy import func
from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import ensure_workspace_for_user, is_platform_admin, sync_user_role_flags
from app.services.activity_service import build_user_audit_snapshot, log_action
from app.services.regulation_ingestion import crawl_active_regulation_sources, derive_source_freshness
from app.models import (
    User, Product, LabelVersion, ComplianceCheck, ComplianceRule,
    Alert, AlertStatus, AlertType, RegulationChange, Severity, CheckResult,
    PublishedAlert, PublishedAlertSeverity, PublishedAlertStatus,
    ComplianceReport, PlanType, UserRole, Subscription, PaymentRecord,
    RegulationSource, RegulationCrawlRun,
)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_admin(request: Request, db: Session):
    """Returns (user, None) if admin; else (None, RedirectResponse)."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    sync_user_role_flags(user)
    if not is_platform_admin(user):
        return None, RedirectResponse(url="/dashboard")
    return user, None


# ── Root redirect ────────────────────────────────────────────────────────────

@router.get("")
async def admin_root(request: Request):
    return RedirectResponse(url="/admin/dashboard")


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    total_users    = db.query(User).count()
    active_users   = db.query(User).filter(User.is_active == True).count()
    total_products = db.query(Product).filter(Product.is_active == True).count()
    total_labels   = db.query(LabelVersion).count()
    total_alerts   = db.query(Alert).count()
    unread_alerts  = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()
    total_rules    = db.query(ComplianceRule).filter(ComplianceRule.active == True).count()
    total_reg_changes = db.query(RegulationChange).count()

    total_checks  = db.query(ComplianceCheck).count()
    passed_checks = db.query(ComplianceCheck).filter(ComplianceCheck.result == CheckResult.PASS).count()
    compliance_rate = round((passed_checks / total_checks) * 100) if total_checks else 0

    total_scans   = db.query(LabelVersion).count()
    total_reports = db.query(ComplianceReport).count()
    growth_users  = db.query(User).filter(User.plan == PlanType.GROWTH).count()
    revenue_estimate = growth_users * 2999

    recent_users   = db.query(User).order_by(User.created_at.desc()).limit(6).all()
    recent_alerts  = db.query(Alert).order_by(Alert.created_at.desc()).limit(6).all()
    recent_signups = db.query(User).order_by(User.created_at.desc()).limit(5).all()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "stats": {
            "total_users": total_users,
            "active_users": active_users,
            "total_products": total_products,
            "total_labels": total_labels,
            "total_alerts": total_alerts,
            "unread_alerts": unread_alerts,
            "compliance_rate": compliance_rate,
            "total_checks": total_checks,
            "total_rules": total_rules,
            "total_reg_changes": total_reg_changes,
            "total_scans": total_scans,
            "total_reports": total_reports,
            "growth_users": growth_users,
            "revenue_estimate": revenue_estimate,
        },
        "recent_users": recent_users,
        "recent_alerts": recent_alerts,
        "recent_signups": recent_signups,
    })


# ── Users ─────────────────────────────────────────────────────────────────────

DEMO_EMAILS = {"admin", "ben", "editor", "viewer", "consultant"}


@router.get("/users")
async def admin_users(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    users = db.query(User).order_by(User.created_at.desc()).all()
    user_stats = []
    for u in users:
        if u.account_id:
            product_count = db.query(Product).filter(Product.account_id == u.account_id).count()
            label_count = (
                db.query(LabelVersion)
                .join(Product, Product.id == LabelVersion.product_id)
                .filter(Product.account_id == u.account_id)
                .count()
            )
        else:
            product_count = db.query(Product).filter(Product.user_id == u.id).count()
            label_count = (
                db.query(LabelVersion)
                .join(Product, Product.id == LabelVersion.product_id)
                .filter(Product.user_id == u.id)
                .count()
            )
        user_stats.append({
            "user": u,
            "product_count": product_count,
            "label_count": label_count,
            "is_demo": u.email in DEMO_EMAILS,
            "company_sort": (u.company_name or "").strip().lower(),
        })
    user_stats.sort(key=lambda row: row["company_sort"])

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "user": user,
        "user_stats": user_stats,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != user.id:   # cannot deactivate yourself
        target.is_active = not target.is_active
        db.commit()
        status = "activated" if target.is_active else "deactivated"
        return RedirectResponse(
            url=f"/admin/users?msg=User+{status}+successfully&type=success",
            status_code=302
        )
    return RedirectResponse(url="/admin/users?msg=Action+not+allowed&type=error", status_code=302)


@router.post("/users/{user_id}/toggle-admin")
async def toggle_user_admin(user_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != user.id:
        target.role = (
            UserRole.ACCOUNT_ADMIN
            if target.role == UserRole.SUPER_ADMIN
            else UserRole.SUPER_ADMIN
        )
        sync_user_role_flags(target)
        ensure_workspace_for_user(db, target)
        db.commit()
        action = "granted" if target.role == UserRole.SUPER_ADMIN else "revoked"
        return RedirectResponse(
            url=f"/admin/users?msg=Admin+access+{action}&type=success",
            status_code=302
        )
    return RedirectResponse(url="/admin/users?msg=Action+not+allowed&type=error", status_code=302)


@router.post("/users/create")
async def admin_create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("viewer"),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    # Check if email already taken
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse(
            url="/admin/users?msg=Email+already+registered&type=error",
            status_code=302,
        )

    from app.routes.auth import hash_password

    try:
        new_role = UserRole(role)
    except ValueError:
        new_role = UserRole.VIEWER

    new_user = User(
        name=name.strip(),
        email=email.strip().lower(),
        hashed_password=hash_password(password),
        role=new_role,
        is_active=True,
        onboarding_complete=True,
    )
    sync_user_role_flags(new_user)
    db.add(new_user)
    db.flush()
    ensure_workspace_for_user(db, new_user)
    db.commit()

    role_label = new_role.value.replace("_", " ").title()
    return RedirectResponse(
        url=f"/admin/users?msg=User+{name.strip()}+created+as+{role_label}&type=success",
        status_code=302,
    )


@router.post("/users/{user_id}/change-role")
async def change_user_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    target = db.query(User).filter(User.id == user_id).first()
    if not target or target.id == user.id:
        return RedirectResponse(url="/admin/users?msg=Action+not+allowed&type=error", status_code=302)

    try:
        new_role = UserRole(role)
    except ValueError:
        return RedirectResponse(url="/admin/users?msg=Invalid+role&type=error", status_code=302)

    target.role = new_role
    sync_user_role_flags(target)
    ensure_workspace_for_user(db, target)
    db.commit()

    role_label = new_role.value.replace("_", " ").title()
    return RedirectResponse(
        url=f"/admin/users?msg=Role+changed+to+{role_label}&type=success",
        status_code=302,
    )


# ── Products (all accounts) ──────────────────────────────────────────────────

@router.get("/products")
async def admin_products(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    # Get all users who have products, with their products

    users_with_products = (
        db.query(User)
        .filter(User.is_active == True)
        .order_by(User.name)
        .all()
    )

    accounts = []
    for u in users_with_products:
        products_query = db.query(Product).filter(Product.is_active == True)
        if u.account_id:
            products_query = products_query.filter(Product.account_id == u.account_id)
        else:
            products_query = products_query.filter(Product.user_id == u.id)
        products = products_query.order_by(Product.created_at.desc()).all()
        if products:
            accounts.append({"user": u, "products": products})

    total_products = sum(len(a["products"]) for a in accounts)
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/products.html", {
        "request": request,
        "user": user,
        "accounts": accounts,
        "total_products": total_products,
        "unread_alerts": unread_alerts,
    })


# ── Compliance Rules ──────────────────────────────────────────────────────────

@router.get("/rules")
async def admin_rules(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    rules = db.query(ComplianceRule).order_by(ComplianceRule.category, ComplianceRule.rule_code).all()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/rules.html", {
        "request": request,
        "user": user,
        "rules": rules,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/rules/{rule_id}/toggle-active")
async def toggle_rule_active(rule_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    rule = db.query(ComplianceRule).filter(ComplianceRule.id == rule_id).first()
    if rule:
        rule.active = not rule.active
        db.commit()
        status = "enabled" if rule.active else "disabled"
        return RedirectResponse(
            url=f"/admin/rules?msg=Rule+{status}&type=success",
            status_code=302
        )
    return RedirectResponse(url="/admin/rules", status_code=302)


@router.post("/rules/{rule_id}/edit")
async def edit_rule(rule_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    form = await request.form()
    rule = db.query(ComplianceRule).filter(ComplianceRule.id == rule_id).first()
    if rule:
        if form.get("severity"):
            try:
                rule.severity = Severity(form["severity"])
            except ValueError:
                pass
        if form.get("description"):
            rule.description = form["description"].strip()
        if form.get("remediation_template") is not None:
            rule.remediation_template = form["remediation_template"].strip()
        db.commit()

    return RedirectResponse(
        url="/admin/rules?msg=Rule+updated+successfully&type=success",
        status_code=302
    )


# ── Regulations Knowledge ─────────────────────────────────────────────────────

@router.get("/regulations-kb")
async def admin_regulations_kb_redirect(request: Request):
    """Consolidated into the LLM Train page."""
    return RedirectResponse(url="/admin/llm/regulations/train", status_code=301)


@router.post("/regulations-kb/sync-rules")
async def admin_sync_rules_redirect(request: Request):
    return RedirectResponse(url="/admin/llm/regulations/sync-rules", status_code=307)


@router.post("/regulations-kb/seed-llm")
async def admin_seed_llm_redirect(request: Request):
    return RedirectResponse(url="/admin/llm/regulations/seed", status_code=307)


@router.post("/regulations-kb/reseed-llm")
async def admin_reseed_llm_redirect(request: Request):
    return RedirectResponse(url="/admin/llm/regulations/reset", status_code=307)


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def admin_alerts(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    severity_filter = request.query_params.get("severity", "")
    type_filter     = request.query_params.get("type", "")
    status_filter   = request.query_params.get("status", "")

    q = db.query(Alert)
    if severity_filter:
        try:
            q = q.filter(Alert.severity == Severity(severity_filter))
        except ValueError:
            pass
    if type_filter:
        try:
            q = q.filter(Alert.alert_type == AlertType(type_filter))
        except ValueError:
            pass
    if status_filter:
        try:
            q = q.filter(Alert.status == AlertStatus(status_filter))
        except ValueError:
            pass

    alerts_list   = q.order_by(Alert.created_at.desc()).all()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/alerts.html", {
        "request": request,
        "user": user,
        "alerts": alerts_list,
        "unread_alerts": unread_alerts,
        "filter_severity": severity_filter,
        "filter_type": type_filter,
        "filter_status": status_filter,
        "alert_types": [t.value for t in AlertType],
    })


@router.post("/alerts/{alert_id}/mark-read")
async def mark_alert_read(alert_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.status = AlertStatus.ACKNOWLEDGED
        db.commit()
    return RedirectResponse(url="/admin/alerts", status_code=302)


# ── System Controls ───────────────────────────────────────────────────────────

@router.get("/system")
async def admin_system(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.config import get_settings
    cfg = get_settings()

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    db_stats = {
        "users":             db.query(User).count(),
        "products":          db.query(Product).count(),
        "label_versions":    db.query(LabelVersion).count(),
        "compliance_checks": db.query(ComplianceCheck).count(),
        "compliance_rules":  db.query(ComplianceRule).count(),
        "regulation_changes":db.query(RegulationChange).count(),
        "regulation_sources": db.query(RegulationSource).count(),
        "crawl_runs":        db.query(RegulationCrawlRun).count(),
        "alerts":            db.query(Alert).count(),
    }

    source_rows = db.query(RegulationSource).order_by(RegulationSource.name.asc()).all()
    source_summary = {
        "total": len(source_rows),
        "fresh": 0,
        "stale": 0,
        "degraded": 0,
        "never": 0,
    }
    for source in source_rows:
        state = derive_source_freshness(source)
        source.freshness_state = state
        source_summary[state] = source_summary.get(state, 0) + 1

    env_info = {
        "app_name":              cfg.app_name,
        "debug":                 cfg.debug,
        "upload_dir":            cfg.upload_dir,
        "brevo_configured":      bool(cfg.brevo_smtp_user),
        "gemini_configured":     bool(cfg.gemini_api_key),
        "admin_email_set":       bool(cfg.admin_email),
        "scrape_schedule":       "Daily at 6:00 AM IST",
    }

    return templates.TemplateResponse("admin/system.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "db_stats": db_stats,
        "env_info": env_info,
        "source_summary": source_summary,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.get("/regulations/sources")
async def admin_regulation_sources(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    sources = db.query(RegulationSource).order_by(RegulationSource.name.asc()).all()
    for source in sources:
        source.freshness_state = derive_source_freshness(source)

    recent_runs = (
        db.query(RegulationCrawlRun)
        .options(joinedload(RegulationCrawlRun.source))
        .order_by(RegulationCrawlRun.started_at.desc())
        .limit(12)
        .all()
    )
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    summary = {
        "total": len(sources),
        "fresh": sum(1 for source in sources if source.freshness_state == "fresh"),
        "stale": sum(1 for source in sources if source.freshness_state == "stale"),
        "degraded": sum(1 for source in sources if source.freshness_state == "degraded"),
        "never": sum(1 for source in sources if source.freshness_state == "never"),
    }

    return templates.TemplateResponse("admin/regulation_sources.html", {
        "request": request,
        "user": user,
        "sources": sources,
        "recent_runs": recent_runs,
        "summary": summary,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/regulations/sources/{source_id}/refresh")
async def admin_refresh_regulation_source(source_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    source = db.query(RegulationSource).filter(RegulationSource.id == source_id).first()
    if not source:
        return RedirectResponse(url="/admin/regulations/sources?msg=Unknown+source&type=error", status_code=302)

    result = crawl_active_regulation_sources(db, source_ids=[source_id], initiated_by="manual")
    message = (
        f"Refreshed {source.name}: {result['accepted_count']} accepted, "
        f"{result['reject_count']} rejected, {result['unchanged_count']} unchanged"
    )
    return RedirectResponse(
        url=f"/admin/regulations/sources?msg={quote_plus(message)}&type=success",
        status_code=302,
    )


@router.post("/regulations/refresh-all")
async def admin_refresh_all_regulation_sources(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    result = crawl_active_regulation_sources(db, initiated_by="manual")
    message = (
        f"Refreshed {result['source_count']} sources: {result['accepted_count']} accepted, "
        f"{result['reject_count']} rejected, {result['unchanged_count']} unchanged"
    )
    return RedirectResponse(
        url=f"/admin/regulations/sources?msg={quote_plus(message)}&type=success",
        status_code=302,
    )


@router.post("/trigger-scrape")
async def admin_trigger_scrape(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    try:
        result = crawl_active_regulation_sources(db, initiated_by="manual")
        msg = quote_plus(
            f"Regulation refresh complete: {result['accepted_count']} accepted, "
            f"{result['reject_count']} rejected, {result['unchanged_count']} unchanged"
        )
        t = "success"
    except Exception as e:
        msg = quote_plus(f"Could not run regulation refresh: {str(e)[:120]}")
        t = "error"

    return RedirectResponse(url=f"/admin/system?msg={msg}&type={t}", status_code=302)


@router.post("/trigger-recheck")
async def admin_trigger_recheck(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    try:
        from app.workers.recheck_task import recheck_all_labels
        recheck_all_labels.delay()
        msg = "Label+re-check+job+queued+—+all+products+will+be+re-evaluated"
        t = "success"
    except Exception as e:
        msg = f"Could+not+queue+re-check:+{str(e)[:80].replace(' ', '+')}"
        t = "error"

    return RedirectResponse(url=f"/admin/system?msg={msg}&type={t}", status_code=302)


# ── Published Alerts (Regulation Alert Composer) ──────────────────────────────

@router.get("/published-alerts")
async def admin_published_alerts(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    alerts = db.query(PublishedAlert).order_by(PublishedAlert.created_at.desc()).all()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/published_alerts.html", {
        "request": request,
        "user": user,
        "published_alerts": alerts,
        "unread_alerts": unread_alerts,
        "severities": [s.value for s in PublishedAlertSeverity],
        "product_categories": [
            "Health Supplement", "Sports Nutrition", "Herbal/Ayurvedic",
            "Functional Food", "Medical Nutrition", "Infant Nutrition",
            "Vitamin & Mineral Supplement", "Digestive Health", "All Categories"
        ],
    })


@router.post("/published-alerts/create")
async def create_published_alert(
    request: Request,
    title: str = Form(...),
    summary: str = Form(...),
    severity: str = Form(...),
    source_url: str = Form(""),
    source_title: str = Form(""),
    publish_now: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    form_data = await request.form()
    categories = list(form_data.getlist("categories"))

    alert = PublishedAlert(
        title=title,
        summary=summary,
        severity=PublishedAlertSeverity(severity),
        source_url=source_url or None,
        source_title=source_title or None,
        affected_categories=categories,
        status=PublishedAlertStatus.PUBLISHED if publish_now else PublishedAlertStatus.DRAFT,
        published_by=user.id,
        published_at=datetime.utcnow() if publish_now else None,
    )
    db.add(alert)
    db.commit()

    return RedirectResponse(url="/admin/published-alerts", status_code=302)


@router.post("/published-alerts/{alert_id}/publish")
async def publish_alert(alert_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    alert = db.query(PublishedAlert).filter(PublishedAlert.id == alert_id).first()
    if alert:
        alert.status = PublishedAlertStatus.PUBLISHED
        alert.published_at = datetime.utcnow()
        alert.published_by = user.id
        db.commit()

    return RedirectResponse(url="/admin/published-alerts", status_code=302)


@router.post("/published-alerts/{alert_id}/archive")
async def archive_alert(alert_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    alert = db.query(PublishedAlert).filter(PublishedAlert.id == alert_id).first()
    if alert:
        alert.status = PublishedAlertStatus.ARCHIVED
        db.commit()

    return RedirectResponse(url="/admin/published-alerts", status_code=302)


# ── Activity Log ──────────────────────────────────────────────────────────────

@router.get("/activity")
async def activity_log(request: Request, db: Session = Depends(get_db)):
    user, redir = _require_admin(request, db)
    if redir:
        return redir
    from app.models import ActivityLog
    from datetime import timedelta

    since = request.query_params.get("since", "")
    page = int(request.query_params.get("page", 1))
    per_page = 50

    q = db.query(ActivityLog)
    if since == "24h":
        cutoff = datetime.utcnow() - timedelta(hours=24)
        q = q.filter(ActivityLog.created_at >= cutoff)
    elif since == "7d":
        cutoff = datetime.utcnow() - timedelta(days=7)
        q = q.filter(ActivityLog.created_at >= cutoff)

    total = q.count()
    logs = (
        q
        .order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    # eager-load user names
    for log in logs:
        _ = log.user

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()
    return templates.TemplateResponse("admin/activity_log.html", {
        "request": request,
        "user": user,
        "logs": logs,
        "page": page,
        "total": total,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "unread_alerts": unread_alerts,
        "since": since,
    })


# ── User Detail ───────────────────────────────────────────────────────────────

@router.get("/users/{user_id}")
async def admin_user_detail(user_id: int, request: Request, db: Session = Depends(get_db)):
    user, redir = _require_admin(request, db)
    if redir:
        return redir
    from app.models import ActivityLog, ComplianceReport

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(url="/admin/users?msg=User+not+found&type=error")
    products_query = db.query(Product).filter(Product.is_active == True)
    if target.account_id:
        products_query = products_query.filter(Product.account_id == target.account_id)
    else:
        products_query = products_query.filter(Product.user_id == user_id)
    products = products_query.all()
    recent_activity = (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == user_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(20)
        .all()
    )
    report_query = db.query(ComplianceReport)
    if target.account_id:
        report_query = report_query.filter(ComplianceReport.account_id == target.account_id)
    else:
        report_query = report_query.filter(ComplianceReport.user_id == user_id)
    report_count = report_query.count()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()
    return templates.TemplateResponse("admin/user_detail.html", {
        "request": request,
        "user": user,
        "target": target,
        "products": products,
        "recent_activity": recent_activity,
        "report_count": report_count,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.get("/users/{user_id}/audit")
async def admin_user_audit(user_id: int, request: Request, db: Session = Depends(get_db)):
    user, redir = _require_admin(request, db)
    if redir:
        return redir

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(url="/admin/users?msg=User+not+found&type=error")

    snapshot = build_user_audit_snapshot(db, target, limit=40)
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()
    return templates.TemplateResponse("admin/user_audit.html", {
        "request": request,
        "user": user,
        "target": target,
        "snapshot": snapshot,
        "unread_alerts": unread_alerts,
    })


@router.post("/users/{user_id}/toggle-admin-detail")
async def admin_toggle_admin(user_id: int, request: Request, db: Session = Depends(get_db)):
    user, redir = _require_admin(request, db)
    if redir:
        return redir
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != user.id:  # can't demote yourself
        new_role = (
            UserRole.ACCOUNT_ADMIN
            if target.role == UserRole.SUPER_ADMIN
            else UserRole.SUPER_ADMIN
        )
        target.role = new_role
        sync_user_role_flags(target)
        ensure_workspace_for_user(db, target)
        db.commit()
        log_action(
            user.id,
            "admin_role_updated",
            "user",
            target.id,
            detail=f"Changed admin role for {target.email} to {new_role.value}",
            request=request,
            target_user_id=target.id,
            context={"new_role": new_role.value},
        )
    return RedirectResponse(url=f"/admin/users/{user_id}?msg=Updated&type=success", status_code=302)


@router.post("/users/{user_id}/toggle-active-detail")
async def admin_toggle_active(user_id: int, request: Request, db: Session = Depends(get_db)):
    user, redir = _require_admin(request, db)
    if redir:
        return redir
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != user.id:  # can't deactivate yourself
        target.is_active = not target.is_active
        db.commit()
        log_action(
            user.id,
            "admin_status_updated",
            "user",
            target.id,
            detail=f"{'Activated' if target.is_active else 'Suspended'} {target.email}",
            request=request,
            target_user_id=target.id,
            context={"is_active": target.is_active},
        )
    return RedirectResponse(url=f"/admin/users/{user_id}?msg=Updated&type=success", status_code=302)


# ── Blog Management — handled entirely by app/routes/blog.py ─────────────────


# ── API Usage Reporting ───────────────────────────────────────────────────────

@router.get("/api-usage")
async def admin_api_usage(
    request: Request,
    db: Session = Depends(get_db),
    period: str = "30d",        # "today", "7d", "30d", "90d", "custom"
    date_from: str = None,      # YYYY-MM-DD
    date_to: str = None,        # YYYY-MM-DD
):
    from datetime import timedelta, date as date_cls

    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    COST_RATES = {
        "gemma":    {"in": 0.10,  "out": 0.40},   # OpenRouter gemma-4-31b $/1M tokens
        "claude":   {"in": 3.00,  "out": 15.00},   # claude-sonnet-4-6 $/1M tokens
        "gemini":   {"in": 0.075, "out": 0.30},    # gemini-3.1-flash-lite $/1M tokens
        "local":    {"in": 0.0,   "out": 0.0},
        "fallback": {"in": 0.0,   "out": 0.0},
    }

    # Date range logic — use IST (UTC+5:30) for date grouping
    _IST = timedelta(hours=5, minutes=30)
    today = (datetime.utcnow() + _IST).date()
    if period == "today":
        start_date = today
        end_date = today
    elif period == "7d":
        start_date = today - timedelta(days=6)
        end_date = today
    elif period == "90d":
        start_date = today - timedelta(days=89)
        end_date = today
    elif period == "custom" and date_from and date_to:
        start_date = date_cls.fromisoformat(date_from)
        end_date = date_cls.fromisoformat(date_to)
    else:  # default 30d
        period = "30d"
        start_date = today - timedelta(days=29)
        end_date = today

    # Convert IST date boundaries → UTC for DB queries (DB stores UTC timestamps)
    cutoff = datetime.combine(start_date, datetime.min.time()) - _IST
    cutoff_end = datetime.combine(end_date, datetime.max.time()) - _IST

    # Totals scoped to date range
    base_q = db.query(LabelVersion).filter(
        LabelVersion.uploaded_at >= cutoff,
        LabelVersion.uploaded_at <= cutoff_end,
    )
    total_scans = base_q.count()

    source_counts = {}
    for src in ["gemma", "claude", "gemini", "local", "fallback"]:
        source_counts[src] = base_q.filter(LabelVersion.extraction_source == src).count()

    # Token totals by source for cost calculation
    token_by_source = (
        db.query(
            LabelVersion.extraction_source,
            func.coalesce(func.sum(LabelVersion.tokens_input), 0).label("inp"),
            func.coalesce(func.sum(LabelVersion.tokens_output), 0).label("out"),
            func.count(LabelVersion.id).label("cnt"),
            func.coalesce(func.avg(LabelVersion.extraction_confidence), 0).label("avg_conf"),
        )
        .filter(LabelVersion.uploaded_at >= cutoff, LabelVersion.uploaded_at <= cutoff_end)
        .group_by(LabelVersion.extraction_source)
        .all()
    )

    provider_stats = []
    total_ai_cost = 0.0
    for row in token_by_source:
        src = row.extraction_source or "fallback"
        rate = COST_RATES.get(src, {"in": 0, "out": 0})
        cost = (int(row.inp) / 1_000_000) * rate["in"] + (int(row.out) / 1_000_000) * rate["out"]
        total_ai_cost += cost
        provider_stats.append({
            "source": src,
            "scans": row.cnt,
            "tokens_in": int(row.inp),
            "tokens_out": int(row.out),
            "cost_usd": round(cost, 4),
            "avg_confidence": round(float(row.avg_conf or 0), 2),
            "cost_per_scan": round(cost / max(row.cnt, 1), 5),
        })
    provider_stats.sort(key=lambda x: x["cost_usd"], reverse=True)

    def _new_usage_bucket():
        return {"total": 0, "gemma": 0, "claude": 0, "gemini": 0, "local": 0, "fallback": 0, "cost": 0.0}

    scan_rows = (
        db.query(
            LabelVersion.uploaded_at,
            LabelVersion.extraction_source,
            LabelVersion.tokens_input,
            LabelVersion.tokens_output,
        )
        .filter(LabelVersion.uploaded_at >= cutoff, LabelVersion.uploaded_at <= cutoff_end)
        .all()
    )

    daily: dict = {}
    hourly: dict = {}
    for uploaded_at, extraction_source, tokens_input, tokens_output in scan_rows:
        if not uploaded_at:
            continue
        ist_dt = uploaded_at + _IST
        src = extraction_source or "fallback"
        inp = int(tokens_input or 0)
        out = int(tokens_output or 0)
        rate = COST_RATES.get(src, {"in": 0, "out": 0})
        cost = (inp / 1_000_000) * rate["in"] + (out / 1_000_000) * rate["out"]

        day = str(ist_dt.date())
        day_bucket = daily.setdefault(day, _new_usage_bucket())
        day_bucket[src] = day_bucket.get(src, 0) + 1
        day_bucket["total"] += 1
        day_bucket["cost"] += cost

        if period == "today":
            hour = int(ist_dt.hour)
            hour_bucket = hourly.setdefault(hour, _new_usage_bucket())
            hour_bucket[src] = hour_bucket.get(src, 0) + 1
            hour_bucket["total"] += 1
            hour_bucket["cost"] += cost

    # Fill missing days with zeros
    all_days = []
    d = start_date
    while d <= end_date:
        ds = str(d)
        all_days.append({"day": ds, **daily.get(ds, _new_usage_bucket())})
        d += timedelta(days=1)

    # ── Hourly breakdown (only for "today" period) ──────────────────────────
    hourly_list = []
    if period == "today":
        for h in range(24):
            label = f"{h:02d}:00"
            hourly_list.append({
                "hour": label,
                **hourly.get(h, _new_usage_bucket()),
            })

    # Most used provider
    most_used = max(source_counts, key=lambda s: source_counts[s]) if total_scans > 0 else "—"

    # Overall avg confidence
    conf_row = (
        db.query(func.coalesce(func.avg(LabelVersion.extraction_confidence), 0))
        .filter(LabelVersion.uploaded_at >= cutoff, LabelVersion.uploaded_at <= cutoff_end)
        .scalar()
    )
    overall_avg_conf = round(float(conf_row or 0), 2)

    # ── Other LLM call stats (kb_chat, compliance_format, query_expansion) ──────
    from app.models import APICallLog
    other_call_stats = []
    total_other_cost = 0.0
    try:
        other_rows = (
            db.query(
                APICallLog.call_type,
                APICallLog.provider,
                func.count(APICallLog.id).label("cnt"),
                func.coalesce(func.sum(APICallLog.tokens_input), 0).label("inp"),
                func.coalesce(func.sum(APICallLog.tokens_output), 0).label("out"),
                func.coalesce(func.sum(APICallLog.cost_usd), 0).label("cost"),
            )
            .filter(APICallLog.created_at >= cutoff, APICallLog.created_at <= cutoff_end)
            .group_by(APICallLog.call_type, APICallLog.provider)
            .all()
        )
        for row in other_rows:
            cost = float(row.cost or 0)
            total_other_cost += cost
            other_call_stats.append({
                "call_type": row.call_type,
                "provider": row.provider,
                "count": row.cnt,
                "tokens_in": int(row.inp),
                "tokens_out": int(row.out),
                "cost_usd": round(cost, 5),
            })
        other_call_stats.sort(key=lambda x: x["cost_usd"], reverse=True)
    except Exception:
        pass  # Table may not exist on older deployments

    return templates.TemplateResponse("admin/api_usage.html", {
        "request": request, "user": user, "unread_alerts": unread_alerts,
        "period": period,
        "date_from": str(start_date), "date_to": str(end_date),
        "total_scans": total_scans,
        "provider_stats": provider_stats,
        "total_ai_cost": round(total_ai_cost, 4),
        "daily_list": all_days,
        "cost_rates": COST_RATES,
        "avg_cost_per_scan": round(total_ai_cost / max(total_scans, 1), 5),
        "most_used_provider": most_used,
        "overall_avg_conf": overall_avg_conf,
        "source_counts": source_counts,
        "hourly_list": hourly_list,
        "other_call_stats": other_call_stats,
        "total_other_cost": round(total_other_cost, 4),
        "total_combined_cost": round(total_ai_cost + total_other_cost, 4),
    })


@router.get("/finance")
async def admin_finance(
    request: Request,
    db: Session = Depends(get_db),
    period: str = "30d",
    date_from: str = None,
    date_to: str = None,
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from datetime import datetime, timedelta, date as date_cls
    from sqlalchemy import func

    today = datetime.utcnow().date()
    if period == "today":
        start_date = today
        end_date = today
    elif period == "7d":
        start_date = today - timedelta(days=6)
        end_date = today
    elif period == "90d":
        start_date = today - timedelta(days=89)
        end_date = today
    elif period == "all":
        # oldest user signup
        first = db.query(func.min(User.created_at)).scalar()
        start_date = first.date() if first else today - timedelta(days=365)
        end_date = today
    elif period == "custom" and date_from and date_to:
        start_date = date_cls.fromisoformat(date_from)
        end_date = date_cls.fromisoformat(date_to)
    else:
        period = "30d"
        start_date = today - timedelta(days=29)
        end_date = today

    cutoff = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    cutoff_end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

    # ── User / signup stats ─────────────────────────────────────────────────
    total_users = db.query(func.count(User.id)).filter(User.role != UserRole.SUPER_ADMIN).scalar() or 0
    new_users_period = db.query(func.count(User.id)).filter(
        User.created_at >= cutoff, User.created_at <= cutoff_end, User.role != UserRole.SUPER_ADMIN
    ).scalar() or 0

    # Daily signups
    signup_rows = (
        db.query(func.date(User.created_at).label("day"), func.count(User.id).label("cnt"))
        .filter(User.created_at >= cutoff, User.created_at <= cutoff_end, User.role != UserRole.SUPER_ADMIN)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )
    signup_by_day = {str(r.day): r.cnt for r in signup_rows}

    # ── Revenue stats ───────────────────────────────────────────────────────
    # PaymentRecord.amount_paise is in paise (₹1 = 100 paise)
    total_revenue_paise = db.query(func.coalesce(func.sum(PaymentRecord.amount_paise), 0)).filter(
        PaymentRecord.status == "paid"
    ).scalar() or 0
    period_revenue_paise = db.query(func.coalesce(func.sum(PaymentRecord.amount_paise), 0)).filter(
        PaymentRecord.status == "paid",
        PaymentRecord.created_at >= cutoff,
        PaymentRecord.created_at <= cutoff_end,
    ).scalar() or 0

    # Daily revenue
    revenue_rows = (
        db.query(
            func.date(PaymentRecord.created_at).label("day"),
            func.coalesce(func.sum(PaymentRecord.amount_paise), 0).label("paise"),
            func.count(PaymentRecord.id).label("cnt"),
        )
        .filter(PaymentRecord.status == "paid", PaymentRecord.created_at >= cutoff, PaymentRecord.created_at <= cutoff_end)
        .group_by(func.date(PaymentRecord.created_at))
        .order_by(func.date(PaymentRecord.created_at))
        .all()
    )
    revenue_by_day = {str(r.day): {"inr": int(r.paise) / 100, "cnt": r.cnt} for r in revenue_rows}

    # ── Subscription stats ──────────────────────────────────────────────────
    sub_by_plan = {}
    try:
        plan_rows = (
            db.query(Subscription.plan, func.count(Subscription.id))
            .filter(Subscription.status == "active")
            .group_by(Subscription.plan)
            .all()
        )
        sub_by_plan = {str(p): c for p, c in plan_rows}
    except Exception:
        pass

    active_subs = sum(sub_by_plan.values())

    # ── Build daily list (fill zeros) ───────────────────────────────────────
    daily_list = []
    d = start_date
    while d <= end_date:
        ds = str(d)
        daily_list.append({
            "day": ds,
            "signups": signup_by_day.get(ds, 0),
            "revenue_inr": revenue_by_day.get(ds, {}).get("inr", 0),
            "payments": revenue_by_day.get(ds, {}).get("cnt", 0),
        })
        d += timedelta(days=1)

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/finance.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "period": period,
        "date_from": str(start_date),
        "date_to": str(end_date),
        "total_users": total_users,
        "new_users_period": new_users_period,
        "active_subs": active_subs,
        "sub_by_plan": sub_by_plan,
        "total_revenue_inr": total_revenue_paise / 100,
        "period_revenue_inr": period_revenue_paise / 100,
        "daily_list": daily_list,
    })
