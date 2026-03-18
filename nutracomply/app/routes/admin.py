"""
Super Admin Panel Routes
All routes require is_admin=True on the current user.
Admin is designated by matching ADMIN_EMAIL env var on registration.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import (
    User, Product, LabelVersion, ComplianceCheck, ComplianceRule,
    Alert, AlertStatus, AlertType, RegulationChange, Severity, CheckResult
)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_admin(request: Request, db: Session):
    """Returns (user, None) if admin; else (None, RedirectResponse)."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None, RedirectResponse(url="/login")
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
    total_products = db.query(Product).count()
    total_labels   = db.query(LabelVersion).count()
    total_alerts   = db.query(Alert).count()
    unread_alerts  = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()
    total_rules    = db.query(ComplianceRule).filter(ComplianceRule.active == True).count()
    total_reg_changes = db.query(RegulationChange).count()

    total_checks  = db.query(ComplianceCheck).count()
    passed_checks = db.query(ComplianceCheck).filter(ComplianceCheck.result == CheckResult.PASS).count()
    compliance_rate = round((passed_checks / total_checks) * 100) if total_checks else 0

    recent_users  = db.query(User).order_by(User.created_at.desc()).limit(6).all()
    recent_alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(6).all()

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
        },
        "recent_users": recent_users,
        "recent_alerts": recent_alerts,
    })


# ── Users ─────────────────────────────────────────────────────────────────────

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
        alert.status = AlertStatus.READ
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
