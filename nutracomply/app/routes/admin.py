"""
Super Admin Panel Routes
All routes require is_admin=True on the current user.
Admin is designated by matching ADMIN_EMAIL env var on registration.
"""
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from sqlalchemy import func
from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import (
    User, Product, LabelVersion, ComplianceCheck, ComplianceRule,
    Alert, AlertStatus, AlertType, RegulationChange, Severity, CheckResult,
    PublishedAlert, PublishedAlertSeverity, PublishedAlertStatus,
    ComplianceReport, PlanType, UserRole,
)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_admin(request: Request, db: Session):
    """Returns (user, None) if admin; else (None, RedirectResponse)."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if not user.is_admin:
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
        product_count = db.query(Product).filter(Product.user_id == u.id).count()
        label_count   = (
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
        })

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
        target.is_admin = not target.is_admin
        db.commit()
        action = "granted" if target.is_admin else "revoked"
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
            url=f"/admin/users?msg=Email+already+registered&type=error",
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
        is_admin=new_role in (UserRole.SUPER_ADMIN,),
        is_active=True,
        onboarding_complete=True,
    )
    db.add(new_user)
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
    # Super admin role automatically gets admin flag
    if new_role == UserRole.SUPER_ADMIN:
        target.is_admin = True
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
    from sqlalchemy.orm import joinedload

    users_with_products = (
        db.query(User)
        .filter(User.is_active == True)
        .order_by(User.name)
        .all()
    )

    accounts = []
    for u in users_with_products:
        products = (
            db.query(Product)
            .filter(Product.user_id == u.id, Product.is_active == True)
            .order_by(Product.created_at.desc())
            .all()
        )
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
async def admin_regulations_kb(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import KBDocument, KBChunk, KBType

    # Get all active rules grouped by framework
    rules = db.query(ComplianceRule).filter(ComplianceRule.active == True).order_by(ComplianceRule.rule_code).all()

    fssai_rules = [r for r in rules if r.rule_code.startswith("FSSAI")]
    lm_rules = [r for r in rules if r.rule_code.startswith("LM")]
    ayush_rules = [r for r in rules if r.rule_code.startswith("AYUSH")]

    # Get KB stats
    reg_docs = db.query(KBDocument).filter(
        KBDocument.kb_type == KBType.REGULATIONS,
        KBDocument.is_active == True,
    ).all()
    reg_chunks = db.query(KBChunk).filter(KBChunk.kb_type == KBType.REGULATIONS).count()

    prod_docs = db.query(KBDocument).filter(
        KBDocument.kb_type == KBType.PRODUCTS,
        KBDocument.is_active == True,
    ).count()
    prod_chunks = db.query(KBChunk).filter(KBChunk.kb_type == KBType.PRODUCTS).count()

    # Get regulation changes
    reg_changes = db.query(RegulationChange).order_by(RegulationChange.effective_date.desc()).all()

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/regulations_kb.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "fssai_rules": fssai_rules,
        "lm_rules": lm_rules,
        "ayush_rules": ayush_rules,
        "total_rules": len(rules),
        "reg_docs": reg_docs,
        "reg_chunks": reg_chunks,
        "prod_docs": prod_docs,
        "prod_chunks": prod_chunks,
        "reg_changes": reg_changes,
    })


@router.post("/regulations-kb/sync-rules")
async def admin_sync_rules(request: Request, db: Session = Depends(get_db)):
    """Force-sync all rules from the seed JSON file into the database.
    Inserts any new rules that don't already exist. Never deletes existing data."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    import json

    rules_path = Path(__file__).parent.parent / "data" / "fssai_rules_seed.json"
    with open(rules_path, encoding="utf-8") as f:
        rules_data = json.load(f)

    existing_codes = {r.rule_code for r in db.query(ComplianceRule.rule_code).all()}
    new_rules = [r for r in rules_data if r["rule_code"] not in existing_codes]

    if new_rules:
        for r in new_rules:
            db.add(ComplianceRule(**r))
        db.commit()

    from urllib.parse import quote
    msg = f"Synced {len(new_rules)} new rules. Total: {len(existing_codes) + len(new_rules)} rules in database."
    return RedirectResponse(url=f"/admin/regulations-kb?msg={quote(msg)}&type=success", status_code=302)


@router.post("/regulations-kb/seed-llm")
async def admin_seed_regulations_llm(request: Request, db: Session = Depends(get_db)):
    """Force-seed the Regulations LLM knowledge base from DB data.
    Permanent storage — data is never auto-deleted."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.services.llm_service import seed_regulations_kb
    result = seed_regulations_kb(db)

    from urllib.parse import quote
    msg = f"Regulations KB: {result.get('status', 'done')} — {result.get('document_count', 0)} documents indexed."
    return RedirectResponse(url=f"/admin/regulations-kb?msg={quote(msg)}&type=success", status_code=302)


@router.post("/regulations-kb/reseed-llm")
async def admin_reseed_regulations_llm(request: Request, db: Session = Depends(get_db)):
    """Clear and re-seed the Regulations LLM KB from current DB data.
    Use this when rules have been updated and the KB needs a full refresh."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import KBDocument, KBChunk, KBType

    # Clear existing regulation KB docs (keep products KB intact)
    reg_docs = db.query(KBDocument).filter(KBDocument.kb_type == KBType.REGULATIONS).all()
    for doc in reg_docs:
        db.query(KBChunk).filter(KBChunk.document_id == doc.id).delete()
        db.delete(doc)
    db.commit()

    from app.services.llm_service import seed_regulations_kb
    result = seed_regulations_kb(db)

    from urllib.parse import quote
    msg = f"Re-seeded Regulations KB — {result.get('document_count', 0)} documents indexed from {len(reg_docs)} cleared."
    return RedirectResponse(url=f"/admin/regulations-kb?msg={quote(msg)}&type=success", status_code=302)


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
        "alerts":            db.query(Alert).count(),
    }

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
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/trigger-scrape")
async def admin_trigger_scrape(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    try:
        from app.workers.scrape_task import run_fssai_scrape
        run_fssai_scrape.delay()
        msg = "Scrape+job+queued+—+results+will+appear+in+the+Regulations+feed"
        t = "success"
    except Exception as e:
        msg = f"Could+not+queue+scrape:+{str(e)[:80].replace(' ', '+')}"
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
    products = db.query(Product).filter(Product.user_id == user_id, Product.is_active == True).all()
    recent_activity = (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == user_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(20)
        .all()
    )
    report_count = db.query(ComplianceReport).filter(ComplianceReport.user_id == user_id).count()
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


@router.post("/users/{user_id}/toggle-admin-detail")
async def admin_toggle_admin(user_id: int, request: Request, db: Session = Depends(get_db)):
    user, redir = _require_admin(request, db)
    if redir:
        return redir
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != user.id:  # can't demote yourself
        target.is_admin = not target.is_admin
        db.commit()
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
    return RedirectResponse(url=f"/admin/users/{user_id}?msg=Updated&type=success", status_code=302)


# ── Blog Management ──────────────────────────────────────────────────────────

@router.get("/blog")
async def admin_blog(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogPost, BlogCategory, BlogPostStatus

    status_filter = request.query_params.get("status", "")
    q = db.query(BlogPost)
    if status_filter:
        try:
            q = q.filter(BlogPost.status == BlogPostStatus(status_filter))
        except ValueError:
            pass

    posts = q.order_by(BlogPost.created_at.desc()).all()
    for p in posts:
        _ = p.author
        _ = p.category

    total_posts = db.query(BlogPost).count()
    published_count = db.query(BlogPost).filter(BlogPost.status == BlogPostStatus.PUBLISHED).count()
    draft_count = db.query(BlogPost).filter(BlogPost.status == BlogPostStatus.DRAFT).count()
    total_views = sum(p.views or 0 for p in posts)
    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "categories": categories,
        "unread_alerts": unread_alerts,
        "total_posts": total_posts,
        "published_count": published_count,
        "draft_count": draft_count,
        "total_views": total_views,
        "status_filter": status_filter,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.get("/blog/categories")
async def admin_blog_categories(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogCategory, BlogPost

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    cat_stats = []
    for cat in categories:
        count = db.query(BlogPost).filter(BlogPost.category_id == cat.id).count()
        cat_stats.append({"category": cat, "post_count": count})

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog_categories.html", {
        "request": request,
        "user": user,
        "cat_stats": cat_stats,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/blog/categories/create")
async def admin_create_blog_category(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogCategory
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    existing = db.query(BlogCategory).filter(
        (BlogCategory.name == name) | (BlogCategory.slug == slug)
    ).first()
    if existing:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/admin/blog/categories?msg={quote('Category already exists')}&type=error",
            status_code=302,
        )

    cat = BlogCategory(name=name.strip(), slug=slug, description=description.strip() or None)
    db.add(cat)
    db.commit()

    from urllib.parse import quote
    return RedirectResponse(
        url=f"/admin/blog/categories?msg={quote('Category created')}&type=success",
        status_code=302,
    )


@router.post("/blog/categories/{cat_id}/delete")
async def admin_delete_blog_category(cat_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogCategory, BlogPost

    cat = db.query(BlogCategory).filter(BlogCategory.id == cat_id).first()
    if cat:
        db.query(BlogPost).filter(BlogPost.category_id == cat_id).update({"category_id": None})
        db.delete(cat)
        db.commit()

    return RedirectResponse(url="/admin/blog/categories?msg=Category+deleted&type=success", status_code=302)


@router.get("/blog/new")
async def admin_blog_new(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogCategory

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog_editor.html", {
        "request": request,
        "user": user,
        "categories": categories,
        "unread_alerts": unread_alerts,
        "post": None,
        "editing": False,
    })


@router.post("/blog/create")
async def admin_blog_create(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    excerpt: str = Form(""),
    category_id: str = Form(""),
    featured_image_url: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    tags: str = Form(""),
    is_featured: str = Form(""),
    status: str = Form("draft"),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogPost, BlogPostStatus
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    existing = db.query(BlogPost).filter(BlogPost.slug == slug).first()
    if existing:
        import time
        slug = f"{slug}-{int(time.time()) % 10000}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    post_status = BlogPostStatus.PUBLISHED if status == "published" else BlogPostStatus.DRAFT
    published_at = datetime.utcnow() if post_status == BlogPostStatus.PUBLISHED else None

    post = BlogPost(
        title=title.strip(),
        slug=slug,
        excerpt=excerpt.strip() or None,
        content=content,
        featured_image_url=featured_image_url.strip() or None,
        category_id=int(category_id) if category_id else None,
        author_id=user.id,
        status=post_status,
        meta_title=meta_title.strip() or None,
        meta_description=meta_description.strip() or None,
        tags=tag_list,
        is_featured=bool(is_featured),
        published_at=published_at,
    )
    db.add(post)
    db.commit()

    from urllib.parse import quote
    return RedirectResponse(
        url=f"/admin/blog?msg={quote('Post created successfully')}&type=success",
        status_code=302,
    )


@router.get("/blog/{post_id}/edit")
async def admin_blog_edit(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogPost, BlogCategory

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        return RedirectResponse(url="/admin/blog?msg=Post+not+found&type=error", status_code=302)

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog_editor.html", {
        "request": request,
        "user": user,
        "categories": categories,
        "unread_alerts": unread_alerts,
        "post": post,
        "editing": True,
    })


@router.post("/blog/{post_id}/update")
async def admin_blog_update(
    post_id: int,
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    excerpt: str = Form(""),
    category_id: str = Form(""),
    featured_image_url: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    tags: str = Form(""),
    is_featured: str = Form(""),
    status: str = Form("draft"),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogPost, BlogPostStatus

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        return RedirectResponse(url="/admin/blog?msg=Post+not+found&type=error", status_code=302)

    post.title = title.strip()
    post.content = content
    post.excerpt = excerpt.strip() or None
    post.featured_image_url = featured_image_url.strip() or None
    post.category_id = int(category_id) if category_id else None
    post.meta_title = meta_title.strip() or None
    post.meta_description = meta_description.strip() or None
    post.tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    post.is_featured = bool(is_featured)

    new_status = BlogPostStatus.PUBLISHED if status == "published" else BlogPostStatus(status) if status in ("draft", "archived") else BlogPostStatus.DRAFT
    if new_status == BlogPostStatus.PUBLISHED and post.status != BlogPostStatus.PUBLISHED:
        post.published_at = datetime.utcnow()
    post.status = new_status

    db.commit()

    from urllib.parse import quote
    return RedirectResponse(
        url=f"/admin/blog?msg={quote('Post updated successfully')}&type=success",
        status_code=302,
    )


@router.post("/blog/{post_id}/publish")
async def admin_blog_publish(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogPost, BlogPostStatus

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if post:
        post.status = BlogPostStatus.PUBLISHED
        if not post.published_at:
            post.published_at = datetime.utcnow()
        db.commit()

    return RedirectResponse(url="/admin/blog?msg=Post+published&type=success", status_code=302)


@router.post("/blog/{post_id}/archive")
async def admin_blog_archive(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogPost, BlogPostStatus

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if post:
        post.status = BlogPostStatus.ARCHIVED
        db.commit()

    return RedirectResponse(url="/admin/blog?msg=Post+archived&type=success", status_code=302)


@router.post("/blog/{post_id}/delete")
async def admin_blog_delete(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.models import BlogPost

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if post:
        db.delete(post)
        db.commit()

    return RedirectResponse(url="/admin/blog?msg=Post+deleted&type=success", status_code=302)


# ── API Usage Reporting ───────────────────────────────────────────────────────

@router.get("/api-usage")
async def admin_api_usage(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    # Totals
    total_scans = db.query(LabelVersion).count()
    claude_scans = db.query(LabelVersion).filter(LabelVersion.extraction_source == "claude").count()
    gemma_scans  = db.query(LabelVersion).filter(LabelVersion.extraction_source == "gemma").count()
    gemini_scans = db.query(LabelVersion).filter(LabelVersion.extraction_source == "gemini").count()
    local_scans  = db.query(LabelVersion).filter(LabelVersion.extraction_source == "local").count()
    fallback_scans = db.query(LabelVersion).filter(LabelVersion.extraction_source == "fallback").count()

    token_totals = db.query(
        func.coalesce(func.sum(LabelVersion.tokens_input), 0),
        func.coalesce(func.sum(LabelVersion.tokens_output), 0),
    ).first()
    total_input_tokens  = int(token_totals[0] or 0)
    total_output_tokens = int(token_totals[1] or 0)
    total_tokens = total_input_tokens + total_output_tokens

    # Cost estimate (claude-sonnet-4-6 pricing: $3/M input, $15/M output)
    INPUT_COST_PER_M  = 3.0
    OUTPUT_COST_PER_M = 15.0
    estimated_cost_usd = (
        (total_input_tokens  / 1_000_000) * INPUT_COST_PER_M +
        (total_output_tokens / 1_000_000) * OUTPUT_COST_PER_M
    )

    # Per-scan breakdown (last 100 Claude scans)
    recent_labels = (
        db.query(LabelVersion)
        .filter(LabelVersion.extraction_source == "claude")
        .order_by(LabelVersion.uploaded_at.desc())
        .limit(100)
        .all()
    )

    # Daily aggregates — last 30 days
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=30)
    daily_rows = (
        db.query(
            func.date(LabelVersion.uploaded_at).label("day"),
            LabelVersion.extraction_source,
            func.count(LabelVersion.id).label("scans"),
            func.coalesce(func.sum(LabelVersion.tokens_input), 0).label("inp"),
            func.coalesce(func.sum(LabelVersion.tokens_output), 0).label("out"),
        )
        .filter(LabelVersion.uploaded_at >= cutoff)
        .group_by(func.date(LabelVersion.uploaded_at), LabelVersion.extraction_source)
        .order_by(func.date(LabelVersion.uploaded_at))
        .all()
    )

    # Collapse into per-day dict for template
    daily: dict = {}
    for row in daily_rows:
        day = str(row.day)
        if day not in daily:
            daily[day] = {"claude": 0, "gemma": 0, "gemini": 0, "local": 0, "fallback": 0,
                          "tokens": 0, "cost": 0.0}
        src = row.extraction_source or "fallback"
        daily[day][src] = daily[day].get(src, 0) + row.scans
        t = int(row.inp) + int(row.out)
        daily[day]["tokens"] += t
        daily[day]["cost"] += (
            (int(row.inp) / 1_000_000) * INPUT_COST_PER_M +
            (int(row.out) / 1_000_000) * OUTPUT_COST_PER_M
        )

    daily_list = sorted(
        [{"day": k, **v} for k, v in daily.items()],
        key=lambda x: x["day"]
    )

    return templates.TemplateResponse("admin/api_usage.html", {
        "request": request,
        "user": user,
        "unread_alerts": unread_alerts,
        "total_scans": total_scans,
        "claude_scans": claude_scans,
        "gemma_scans": gemma_scans,
        "gemini_scans": gemini_scans,
        "local_scans": local_scans,
        "fallback_scans": fallback_scans,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 4),
        "recent_labels": recent_labels,
        "daily_list": daily_list,
    })
