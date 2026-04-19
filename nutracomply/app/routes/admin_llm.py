"""
LLM Studio — Admin routes
=========================
All routes require is_admin=True.
Provides knowledge-base management (train) and chat test interfaces for
the Regulations LLM (gemini-2.5-pro) and Products LLM (gemini-3.1-flash-lite-preview),
with Claude (Anthropic) as automatic fallback.
"""
from pathlib import Path
import uuid
import time as _time

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie

# ── In-memory extraction job store (admin-only, single-process) ────────────
_EXTRACTION_JOBS: dict = {}   # job_id → state dict

# ── Benchmark job store ──────────────────────────────────────────────────────
_BENCHMARK_JOBS: dict = {}   # job_id → {done, results: list, error, started_at}

# ── KB upload job store ──────────────────────────────────────────────────────
_UPLOAD_JOBS: dict = {}   # job_id → {status, filename, chunks, error, started_at}

router    = APIRouter(prefix="/admin")
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)

_VALID_KB = {"regulations", "products"}


def _require_admin(request: Request, db: Session):
    """Returns (user, None) if admin; else (None, RedirectResponse)."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if not user.is_admin:
        return None, RedirectResponse(url="/dashboard", status_code=302)
    return user, None


def _unread_alerts(db: Session) -> int:
    from app.models import Alert, AlertStatus
    return db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/llm")
async def llm_dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.services.llm_service import get_kb_stats
    from app.config import get_settings

    settings = get_settings()

    _empty = {"documents": 0, "chunks": 0}
    try:
        reg_stats  = get_kb_stats("regulations", db)
        prod_stats = get_kb_stats("products",    db)
    except Exception:
        reg_stats  = _empty
        prod_stats = _empty

    return templates.TemplateResponse("admin/llm_dashboard.html", {
        "request":            request,
        "user":               user,
        "unread_alerts":      _unread_alerts(db),
        "reg_stats":          reg_stats,
        "prod_stats":         prod_stats,
        "gemma_configured":   bool(settings.gemma_enabled and settings.openrouter_api_key),
        "gemma_model":        settings.gemma_model_name,
        "gemini_configured":  bool(settings.gemini_api_key),
        "claude_configured":  bool(settings.anthropic_api_key),
    })


# ── Provider status / connectivity test ──────────────────────────────────────

@router.get("/llm/provider-status")
async def llm_provider_status(request: Request, db: Session = Depends(get_db)):
    """
    Quick connectivity test for all configured LLM providers.
    Sends a trivial one-token prompt to each; returns JSON with status + error.
    """
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    from app.config import get_settings
    settings = get_settings()

    result = {}

    # ── Test Gemma via OpenRouter ─────────────────────────────────────────────
    if settings.gemma_enabled and settings.openrouter_api_key:
        import httpx as _httpx
        try:
            url = settings.openrouter_api_url.rstrip("/") + "/chat/completions"
            headers = {
                "content-type": "application/json",
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://steadfast-courage-production-0f66.up.railway.app",
                "X-Title": "RegBite",
            }
            payload = {
                "model": settings.gemma_model_name,
                "messages": [{"role": "user", "content": "Reply with one word: OK"}],
                "max_tokens": 5,
                "temperature": 0,
            }
            resp = _httpx.post(url, headers=headers, json=payload, timeout=20.0)
            if resp.status_code == 200:
                result["gemma"] = {"status": "ok", "model": settings.gemma_model_name}
            elif resp.status_code == 429:
                # Rate limited — model is configured correctly, just temporarily throttled
                retry_after = resp.headers.get("Retry-After", "")
                result["gemma"] = {
                    "status": "rate_limited",
                    "code": 429,
                    "retry_after": retry_after,
                    "model": settings.gemma_model_name,
                }
            else:
                try:
                    err = resp.json()
                    msg = err.get("error", {}).get("message") or err.get("message") or resp.text[:300]
                except Exception:
                    msg = resp.text[:300]
                result["gemma"] = {
                    "status": "error",
                    "code": resp.status_code,
                    "error": msg,
                    "model": settings.gemma_model_name,
                }
        except Exception as exc:
            err_msg = str(exc) or repr(exc)
            result["gemma"] = {"status": "error", "error": err_msg[:300], "model": settings.gemma_model_name}
    else:
        result["gemma"] = {"status": "not_configured"}

    # ── Test Claude ───────────────────────────────────────────────────────────
    if settings.anthropic_api_key:
        try:
            import anthropic as _ant
            client = _ant.Anthropic(api_key=settings.anthropic_api_key)
            client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=5,
                messages=[{"role": "user", "content": "Reply: OK"}],
            )
            result["claude"] = {"status": "ok"}
        except Exception as exc:
            err_msg = str(exc) or repr(exc)
            result["claude"] = {"status": "error", "error": err_msg[:300]}
    else:
        result["claude"] = {"status": "not_configured"}

    # ── Test Gemini ───────────────────────────────────────────────────────────
    if settings.gemini_api_key:
        try:
            import google.generativeai as _genai
            _genai.configure(api_key=settings.gemini_api_key)
            m = _genai.GenerativeModel("gemini-2.5-flash")
            m.generate_content("Reply: OK", generation_config={"max_output_tokens": 5})
            result["gemini"] = {"status": "ok"}
        except Exception as exc:
            err_msg = str(exc) or repr(exc)
            result["gemini"] = {"status": "error", "error": err_msg[:300]}
    else:
        result["gemini"] = {"status": "not_configured"}

    return JSONResponse(result)


@router.get("/llm/api-key-stats")
async def llm_api_key_stats(request: Request, db: Session = Depends(get_db)):
    """Return API key stats for all providers — OpenRouter credits, rate limits, config status."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    from app.config import get_settings
    settings = get_settings()
    import httpx as _httpx

    out = {}

    # ── OpenRouter ────────────────────────────────────────────────────────────
    if settings.openrouter_api_key:
        try:
            resp = _httpx.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "HTTP-Referer": "https://steadfast-courage-production-0f66.up.railway.app",
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                d = resp.json().get("data", resp.json())
                usage       = d.get("usage", 0)          # credits used
                limit       = d.get("limit")              # None = unlimited
                is_free     = d.get("is_free_tier", False)
                label       = d.get("label", "")
                rate_limit  = d.get("rate_limit", {})     # {"requests": n, "interval": "10s"}

                remaining   = None if limit is None else max(0, round(limit - usage, 4))
                pct_used    = None if limit is None else round(usage / limit * 100, 1) if limit > 0 else 0

                out["openrouter"] = {
                    "status":     "ok",
                    "label":      label,
                    "model":      settings.gemma_model_name,
                    "usage":      round(usage, 4),
                    "limit":      limit,
                    "remaining":  remaining,
                    "pct_used":   pct_used,
                    "is_free":    is_free,
                    "rate_limit": rate_limit,
                    "enabled":    settings.gemma_enabled,
                }
            else:
                out["openrouter"] = {"status": "error", "code": resp.status_code, "error": resp.text[:200]}
        except Exception as exc:
            out["openrouter"] = {"status": "error", "error": str(exc)[:200]}
    else:
        out["openrouter"] = {"status": "not_configured"}

    # ── Claude (Anthropic) ────────────────────────────────────────────────────
    out["claude"] = {
        "status":    "configured" if settings.anthropic_api_key else "not_configured",
        "model":     "claude-sonnet-4-6",
        "key_hint":  ("sk-ant-..." + settings.anthropic_api_key[-4:]) if settings.anthropic_api_key else None,
    }

    # ── Gemini (Google) ───────────────────────────────────────────────────────
    out["gemini"] = {
        "status":    "configured" if settings.gemini_api_key else "not_configured",
        "models":    "gemini-2.5-flash / gemini-2.5-pro",
        "key_hint":  ("AIza..." + settings.gemini_api_key[-4:]) if settings.gemini_api_key else None,
    }

    return JSONResponse(out)


@router.get("/llm/openrouter-models")
async def llm_openrouter_models(request: Request, db: Session = Depends(get_db)):
    """
    Fetch all Gemma-related models available on OpenRouter for the current API key.
    Returns JSON list so admin can find the exact model slug to configure.
    """
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    from app.config import get_settings
    settings = get_settings()

    if not settings.openrouter_api_key:
        return JSONResponse({"error": "OPENROUTER_API_KEY not configured"}, status_code=400)

    import httpx as _httpx
    try:
        resp = _httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://steadfast-courage-production-0f66.up.railway.app",
            },
            timeout=15.0,
        )
        if not resp.is_success:
            return JSONResponse({"error": f"HTTP {resp.status_code}", "body": resp.text[:500]})

        all_models = resp.json().get("data", [])
        # Filter to Google/Gemma models only
        google_models = [
            {
                "id":          m["id"],
                "name":        m.get("name", m["id"]),
                "context":     m.get("context_length"),
                "pricing_in":  m.get("pricing", {}).get("prompt"),
                "pricing_out": m.get("pricing", {}).get("completion"),
            }
            for m in all_models
            if "google" in m["id"].lower() or "gemma" in m["id"].lower()
        ]
        google_models.sort(key=lambda x: x["id"])
        return JSONResponse({
            "configured_model": settings.gemma_model_name,
            "google_models":    google_models,
            "total_models":     len(all_models),
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:300]}, status_code=500)


# ── KB management (Train) ─────────────────────────────────────────────────────

@router.get("/llm/{kb_type}/train")
async def llm_train(kb_type: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from app.models import KBDocument, KBType
    from app.services.llm_service import get_kb_stats

    documents = (
        db.query(KBDocument)
        .filter(KBDocument.kb_type == KBType(kb_type),
                KBDocument.is_active)
        .order_by(KBDocument.uploaded_at.desc())
        .all()
    )

    # Flash via query params (set by redirect from POST routes)
    flash_message = request.query_params.get("msg", "").replace("+", " ")
    flash_type    = request.query_params.get("type", "info")

    try:
        stats = get_kb_stats(kb_type, db)
    except Exception:
        stats = {"documents": 0, "chunks": 0}

    # Extra context for regulations: compliance rules + regulation changes
    fssai_rules = lm_rules = ayush_rules = []
    total_rules = 0
    reg_changes = []
    if kb_type == "regulations":
        from app.models import ComplianceRule, RegulationChange
        rules = (
            db.query(ComplianceRule)
            .filter(ComplianceRule.active)
            .order_by(ComplianceRule.rule_code)
            .all()
        )
        fssai_rules = [r for r in rules if r.rule_code.startswith("FSSAI")]
        lm_rules    = [r for r in rules if r.rule_code.startswith("LM")]
        ayush_rules = [r for r in rules if r.rule_code.startswith("AYUSH")]
        total_rules = len(rules)
        reg_changes = (
            db.query(RegulationChange)
            .order_by(RegulationChange.effective_date.desc())
            .all()
        )

    return templates.TemplateResponse("admin/llm_train.html", {
        "request":       request,
        "user":          user,
        "unread_alerts": _unread_alerts(db),
        "kb_type":       kb_type,
        "documents":     documents,
        "stats":         stats,
        "flash_message": flash_message or None,
        "flash_type":    flash_type,
        # Regulations-only extras
        "fssai_rules":   fssai_rules,
        "lm_rules":      lm_rules,
        "ayush_rules":   ayush_rules,
        "total_rules":   total_rules,
        "reg_changes":   reg_changes,
    })


@router.post("/llm/{kb_type}/seed")
async def llm_seed(kb_type: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from app.services.llm_service import seed_regulations_kb, seed_products_kb, invalidate_cache

    try:
        if kb_type == "regulations":
            result = seed_regulations_kb(db)
        else:
            result = seed_products_kb(db)

        invalidate_cache(kb_type)

        if result["status"] == "up_to_date":
            msg  = f"Knowledge+base+already+seeded+({result['document_count']}+documents+exist)"
            typ  = "info"
        else:
            msg  = f"seeded:{result['document_count']}".replace(" ", "+")
            typ  = "success"
    except Exception as exc:
        msg = f"Seed+failed:+{str(exc)[:120].replace(' ', '+')}"
        typ = "error"

    return RedirectResponse(
        url=f"/admin/llm/{kb_type}/train?msg={msg}&type={typ}",
        status_code=302,
    )


@router.post("/llm/regulations/sync-rules")
async def llm_sync_rules(request: Request, db: Session = Depends(get_db)):
    """Force-sync all compliance rules from the seed JSON file into the database.
    Inserts new rules and updates severity/active status for existing rules.
    After sync, auto-resolves stale UNREAD alerts whose violations no longer
    have any CRITICAL/HIGH severity rules."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    import json
    from datetime import datetime
    from pathlib import Path as _Path
    from app.models import (
        ComplianceRule as _ComplianceRule,
        Alert, AlertType, AlertStatus, Severity as _Severity,
    )
    from app.services.llm_service import invalidate_cache

    rules_path = _Path(__file__).parent.parent / "data" / "fssai_rules_seed.json"
    try:
        with open(rules_path, encoding="utf-8") as f:
            rules_data = json.load(f)

        # Build map of existing rules for upsert
        existing_map = {
            r.rule_code: r
            for r in db.query(_ComplianceRule).all()
        }
        new_count = 0
        updated_count = 0

        # Valid ComplianceRule column names (for filtering seed JSON keys)
        _valid_cols = {
            c.name for c in _ComplianceRule.__table__.columns if c.name != "id"
        }
        # Map seed JSON keys that differ from model column names
        _key_map = {
            "remediation": "remediation_template",
            "regulation_reference": "regulation_source",
        }

        for r_data in rules_data:
            code = r_data["rule_code"]
            # Remap mismatched keys and filter to valid columns only
            mapped = {}
            for k, v in r_data.items():
                col = _key_map.get(k, k)
                if col in _valid_cols:
                    mapped[col] = v
            if code not in existing_map:
                db.add(_ComplianceRule(**mapped))
                new_count += 1
            else:
                existing = existing_map[code]
                changed = False
                # Sync severity
                seed_sev = r_data.get("severity", "")
                db_sev = existing.severity.value if existing.severity else ""
                if seed_sev and seed_sev != db_sev:
                    existing.severity = seed_sev
                    changed = True
                # Sync active status
                seed_active = r_data.get("active")
                if seed_active is not None and seed_active != existing.active:
                    existing.active = seed_active
                    changed = True
                if changed:
                    updated_count += 1

        db.commit()

        # Auto-resolve stale UNREAD alerts where all remaining violations are
        # MEDIUM or lower (no longer alert-worthy after severity downgrades)
        resolved_count = 0
        deactivated_codes = {
            r["rule_code"] for r in rules_data if r.get("active") is False
        }
        downgraded_codes = set()
        for r_data in rules_data:
            db_rule = existing_map.get(r_data["rule_code"])
            if (
                db_rule
                and db_rule.severity
                and db_rule.severity.value in ("CRITICAL", "HIGH")
                and r_data.get("severity") in ("MEDIUM", "LOW")
            ):
                downgraded_codes.add(r_data["rule_code"])

        stale_codes = deactivated_codes | downgraded_codes
        if stale_codes:
            unread_alerts = (
                db.query(Alert)
                .filter(
                    Alert.status == AlertStatus.UNREAD,
                    Alert.alert_type == AlertType.LABEL_VIOLATION,
                )
                .all()
            )
            for alert in unread_alerts:
                violations = alert.rule_violations or []
                crit_high_remaining = [
                    v for v in violations
                    if v.get("rule_code") not in stale_codes
                    and v.get("severity") in ("CRITICAL", "HIGH")
                ]
                if not crit_high_remaining:
                    alert.status = AlertStatus.RESOLVED
                    alert.resolved_at = datetime.utcnow()
                    resolved_count += 1
            if resolved_count:
                db.commit()

        invalidate_cache("regulations")

        total = len(existing_map) + new_count
        parts = [f"{new_count}+new"]
        if updated_count:
            parts.append(f"{updated_count}+updated")
        if resolved_count:
            parts.append(f"{resolved_count}+stale+alerts+resolved")
        msg = f"Synced+{',+'.join(parts)}.+Total:+{total}+rules."
        typ = "success"
    except Exception as exc:
        msg = f"Sync+failed:+{str(exc)[:120].replace(' ', '+')}"
        typ = "error"

    return RedirectResponse(
        url=f"/admin/llm/regulations/train?msg={msg}&type={typ}",
        status_code=302,
    )


@router.post("/llm/{kb_type}/reset")
async def llm_reset_kb(kb_type: str, request: Request, db: Session = Depends(get_db)):
    """
    Selectively delete a subset of the regulations KB.
    Does NOT auto-reseed — the user should click Auto-Seed from DB afterward.
    subset param: "all" | "fssai" | "ayush" | "legal_metrology"
    """
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from sqlalchemy import or_
    from app.models import KBDocument, KBChunk, KBType
    from app.services.llm_service import invalidate_cache

    form   = await request.form()
    subset = form.get("subset", "all")  # "all" | "fssai" | "ayush" | "legal_metrology"

    try:
        if kb_type != "regulations" or subset == "all":
            # Full wipe for products KB or explicit "all"
            db.query(KBChunk).filter(
                KBChunk.kb_type == KBType(kb_type)).delete(synchronize_session=False)
            db.query(KBDocument).filter(
                KBDocument.kb_type == KBType(kb_type)).delete(synchronize_session=False)
            db.commit()
        else:
            # Selective wipe — match by title prefix (rule codes: FSSAI-*, AYUSH-ASU-*, LM-*)
            if subset == "fssai":
                pattern_filters = or_(
                    KBDocument.source.like("fssai:%"),          # uploaded PDFs
                    KBDocument.title.like("Rule FSSAI%"),       # compliance rules
                    KBDocument.source.like("db:regulation_change:%"),  # regulation changes
                    KBDocument.source.like("db:ingredient:%"),  # ingredients
                )
            elif subset == "ayush":
                pattern_filters = KBDocument.title.like("Rule AYUSH%")
            else:  # legal_metrology
                pattern_filters = KBDocument.title.like("Rule LM%")

            # Delete matching chunks first (FK safety), then docs
            matching_doc_ids = [
                d.id for d in db.query(KBDocument.id).filter(
                    KBDocument.kb_type == KBType.REGULATIONS,
                    pattern_filters,
                ).all()
            ]
            if matching_doc_ids:
                db.query(KBChunk).filter(
                    KBChunk.document_id.in_(matching_doc_ids)
                ).delete(synchronize_session=False)
                db.query(KBDocument).filter(
                    KBDocument.id.in_(matching_doc_ids)
                ).delete(synchronize_session=False)
            db.commit()

        invalidate_cache(kb_type)

        label = {"fssai": "FSSAI", "ayush": "AYUSH",
                 "legal_metrology": "Legal+Metrology", "all": "All"}.get(subset, subset)
        msg = f"deleted:{label}"
        typ = "success"
    except Exception as exc:
        msg = f"Reset+failed:+{str(exc)[:120].replace(' ', '+')}"
        typ = "error"

    return RedirectResponse(
        url=f"/admin/llm/{kb_type}/train?msg={msg}&type={typ}",
        status_code=302,
    )


@router.post("/llm/regulations/ingest-fssai")
async def llm_ingest_fssai(request: Request, db: Session = Depends(get_db)):
    """Bulk-ingest all FSSAI regulation PDFs from the FSSAI/ folder.
    Skips already-ingested files. Safe to run repeatedly."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from app.services.llm_service import ingest_fssai_pdfs

    try:
        result = ingest_fssai_pdfs(db)

        if result["status"] == "up_to_date":
            msg = f"All+{result['total_files']}+FSSAI+PDFs+already+ingested"
            typ = "info"
        elif result["status"] == "done":
            msg = (f"Ingested+{result['ingested']}+new+PDFs"
                   f"+(skipped+{result['skipped']}+already+known,"
                   f"+{result['failed']}+failed)")
            typ = "success"
        elif result["status"] == "error":
            msg = result.get("message", "Unknown+error").replace(" ", "+")
            typ = "error"
        else:
            msg = "No+PDF+files+found+in+FSSAI+folder"
            typ = "warning"
    except Exception as exc:
        msg = f"FSSAI+ingest+failed:+{str(exc)[:120].replace(' ', '+')}"
        typ = "error"

    return RedirectResponse(
        url=f"/admin/llm/regulations/train?msg={msg}&type={typ}",
        status_code=302,
    )


def _run_upload_job(job_id: str, kb_type: str, raw_bytes: bytes,
                    filename: str, display_title: str, source_key: str,
                    content_hash: str, user_id: int):
    """Background thread: extract + ingest one KB document."""
    from app.database import SessionLocal
    from app.services.llm_service import _ingest_document
    db2 = SessionLocal()
    try:
        _UPLOAD_JOBS[job_id]["note"] = "Extracting text…"
        if filename.lower().endswith(".pdf"):
            content = _extract_pdf_content_for_kb(raw_bytes, filename)
        else:
            content = raw_bytes.decode("utf-8", errors="replace")

        content = content.strip()
        if not content:
            _UPLOAD_JOBS[job_id] = {
                "status": "error", "filename": filename,
                "error": "File appears empty or unreadable after extraction",
            }
            return

        _UPLOAD_JOBS[job_id]["note"] = "Chunking and indexing…"
        doc = _ingest_document(
            db2, kb_type,
            title=display_title,
            source=source_key,
            content=content,
            uploaded_by_id=user_id,
            content_hash=content_hash,
        )
        _UPLOAD_JOBS[job_id] = {
            "status": "done",
            "filename": filename,
            "chunks": doc.chunk_count,
        }
    except Exception as exc:
        _UPLOAD_JOBS[job_id] = {
            "status": "error",
            "filename": filename,
            "error": str(exc)[:200],
        }
    finally:
        db2.close()


@router.post("/llm/{kb_type}/upload")
async def llm_upload(
    kb_type: str,
    request: Request,
    db:      Session    = Depends(get_db),
    file:    UploadFile = File(...),
    title:   str        = Form(""),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"status": "error", "error": "Not authorised"}, status_code=401)
    if kb_type not in _VALID_KB:
        return JSONResponse({"status": "error", "error": "Invalid KB type"}, status_code=400)

    from app.models import KBDocument, KBType
    import hashlib
    import threading

    try:
        filename = file.filename or "upload"
        display_title = title.strip() or filename
        raw_bytes = await file.read()

        if not raw_bytes:
            return JSONResponse({"status": "error", "error": "File is empty"})

        # ── Duplicate detection (fast — done synchronously) ──────────────────
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        source_key   = f"upload:{filename}"

        hash_dupe = db.query(KBDocument.id, KBDocument.title).filter(
            KBDocument.kb_type      == KBType(kb_type),
            KBDocument.content_hash == content_hash,
            KBDocument.is_active,
        ).first()
        if hash_dupe:
            return JSONResponse({
                "status": "skipped",
                "filename": filename,
                "message": f"Already indexed as: {(hash_dupe.title or filename)[:80]}",
            })

        name_dupe = db.query(KBDocument.id).filter(
            KBDocument.kb_type   == KBType(kb_type),
            KBDocument.source    == source_key,
            KBDocument.is_active,
        ).first()
        if name_dupe:
            return JSONResponse({
                "status": "skipped",
                "filename": filename,
                "message": "Already indexed (same filename)",
            })

        # ── Start background extraction + ingestion ───────────────────────────
        job_id = str(uuid.uuid4())[:12]
        _UPLOAD_JOBS[job_id] = {
            "status": "processing",
            "filename": filename,
            "note": "Starting…",
        }
        threading.Thread(
            target=_run_upload_job,
            args=(job_id, kb_type, raw_bytes, filename,
                  display_title, source_key, content_hash, user.id),
            daemon=True,
        ).start()

        return JSONResponse({"status": "processing", "job_id": job_id, "filename": filename})

    except Exception as exc:
        return JSONResponse({"status": "error", "error": str(exc)[:200]})


@router.get("/llm/{kb_type}/upload/status/{job_id}")
async def llm_upload_status(kb_type: str, job_id: str, request: Request,
                             db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    job = _UPLOAD_JOBS.get(job_id)
    if not job:
        return JSONResponse({"status": "not_found"})
    return JSONResponse(job)


@router.get("/llm/{kb_type}/doc-count")
async def llm_doc_count(kb_type: str, request: Request, db: Session = Depends(get_db)):
    """Return current doc + chunk counts for live refresh without page reload."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    from app.models import KBDocument, KBChunk, KBType
    try:
        docs   = db.query(KBDocument).filter(KBDocument.kb_type == KBType(kb_type),
                                              KBDocument.is_active).count()
        chunks = db.query(KBChunk).filter(KBChunk.kb_type == KBType(kb_type)).count()
        return JSONResponse({"docs": docs, "chunks": chunks})
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=500)


@router.get("/llm/{kb_type}/audit")
async def llm_audit(kb_type: str, request: Request, db: Session = Depends(get_db)):
    """Return comprehensive KB quality audit stats as JSON."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    from app.models import KBDocument, KBChunk, KBType
    from sqlalchemy import func

    try:
        # Fetch only small metadata columns — no content, no TOAST reads
        rows = (
            db.query(
                KBDocument.id,
                KBDocument.title,
                KBDocument.source,
                KBDocument.chunk_count,
            )
            .filter(KBDocument.kb_type == KBType(kb_type),
                    KBDocument.is_active)
            .all()
        )

        total_docs   = len(rows)
        total_chunks = db.query(func.count(KBChunk.id)).filter(
            KBChunk.kb_type == KBType(kb_type)
        ).scalar() or 0

        zero_chunk = [r for r in rows if r.chunk_count == 0]
        one_chunk  = [r for r in rows if r.chunk_count == 1]
        good       = [r for r in rows if r.chunk_count >= 2]

        # Source breakdown
        source_stats: dict = {}
        for r in rows:
            src = (r.source or "unknown").split(":")[0]
            if src not in source_stats:
                source_stats[src] = {"docs": 0, "chunks": 0}
            source_stats[src]["docs"]   += 1
            source_stats[src]["chunks"] += r.chunk_count

        # Chunk distribution histogram: 0,1,2-5,6-15,16+
        hist = {"0": 0, "1": 0, "2-5": 0, "6-15": 0, "16+": 0}
        for r in rows:
            c = r.chunk_count
            if   c == 0:  hist["0"]    += 1
            elif c == 1:  hist["1"]    += 1
            elif c <= 5:  hist["2-5"]  += 1
            elif c <= 15: hist["6-15"] += 1
            else:         hist["16+"]  += 1

        health_score = round((len(good) / max(total_docs, 1)) * 100, 1)
        avg_chunks   = round(total_chunks / max(total_docs, 1), 1)

        problem_docs = [
            {"id": r.id, "title": (r.title or "")[:80], "source": r.source,
             "chunks": r.chunk_count, "content_len": 0}
            for r in (zero_chunk + one_chunk)[:50]
        ]

        return JSONResponse({
            "total_docs":       total_docs,
            "total_chunks":     total_chunks,
            "avg_chunks":       avg_chunks,
            "health_score":     health_score,
            "zero_chunk_count": len(zero_chunk),
            "one_chunk_count":  len(one_chunk),
            "good_count":       len(good),
            "histogram":        hist,
            "source_stats":     source_stats,
            "problem_docs":     problem_docs,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:300]}, status_code=500)


@router.post("/llm/regulations/clear-and-rebuild")
async def llm_clear_and_rebuild(request: Request, db: Session = Depends(get_db)):
    """
    Nuclear reset for the regulations KB:
    1. Delete ALL KBChunk + KBDocument rows for regulations
    2. Immediately re-seed from DB (compliance rules, ingredients, regulation changes)
    Returns JSON stats so the UI can refresh without a page reload.
    """
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    from app.models import KBDocument, KBChunk, KBType
    from app.services.llm_service import seed_regulations_kb, invalidate_cache

    try:
        # ── Step 1: wipe everything ───────────────────────────────────────────
        chunks_deleted = db.query(KBChunk).filter(
            KBChunk.kb_type == KBType.REGULATIONS
        ).delete(synchronize_session=False)

        docs_deleted = db.query(KBDocument).filter(
            KBDocument.kb_type == KBType.REGULATIONS
        ).delete(synchronize_session=False)

        db.commit()
        invalidate_cache("regulations")

        # ── Step 2: re-seed base context from DB ─────────────────────────────
        seed_result = seed_regulations_kb(db)
        reseeded = seed_result.get("document_count", 0)

        return JSONResponse({
            "status":        "ok",
            "docs_deleted":  docs_deleted,
            "chunks_deleted": chunks_deleted,
            "reseeded":      reseeded,
            "message":       (
                f"Cleared {docs_deleted} documents ({chunks_deleted} chunks). "
                f"Re-seeded {reseeded} base documents from DB. "
                "Ready to upload your .md files."
            ),
        })
    except Exception as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)[:300]}, status_code=500)


@router.get("/llm/{kb_type}/docs-partial")
async def llm_docs_partial(kb_type: str, request: Request, db: Session = Depends(get_db)):
    """Return latest doc list as JSON for live table refresh after upload."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    if kb_type not in _VALID_KB:
        return JSONResponse({"error": "Invalid KB type"}, status_code=400)
    from app.models import KBDocument, KBType
    docs = (
        db.query(KBDocument)
        .filter(KBDocument.kb_type == KBType(kb_type), KBDocument.is_active)
        .order_by(KBDocument.uploaded_at.desc())
        .all()
    )
    return JSONResponse({
        "total": len(docs),
        "docs": [
            {
                "id":          d.id,
                "title":       d.title or "",
                "source":      d.source or "",
                "chunk_count": d.chunk_count,
                "uploaded_at": d.uploaded_at.strftime("%d %b %Y") if d.uploaded_at else "—",
            }
            for d in docs
        ],
    })


# ── KB Rule Extraction job store ─────────────────────────────────────────────
_EXTRACT_JOBS: dict = {}   # job_id → {status, rules, error, note}


def _run_extract_job(job_id: str, content: str, doc_title: str, existing_codes: set):
    """Background thread: call Gemini to extract compliance rules from regulation text."""
    import json as _json
    import google.generativeai as genai
    from app.config import get_settings
    settings = get_settings()
    try:
        _EXTRACT_JOBS[job_id]["note"] = "Calling Gemini…"
        if not settings.gemini_api_key:
            _EXTRACT_JOBS[job_id] = {"status": "error", "error": "Gemini API key not configured"}
            return

        prompt = (
            "You are an FSSAI compliance expert analyzing Indian nutraceutical/health supplement regulations.\n\n"
            f"DOCUMENT: {doc_title}\n\n"
            "REGULATION TEXT:\n"
            f"{content[:9000]}\n\n"
            "Extract ALL specific, objectively verifiable compliance requirements from this text that apply "
            "to product labels for nutraceuticals or health supplements.\n\n"
            "For each requirement output a JSON object with these exact fields:\n"
            "- rule_code: unique code — use prefix FSSAI-NUTRA-, FSSAI-HEALTH-, LM-PKG-, AYUSH-ASU- based on content, "
            "followed by category abbreviation and a 3-digit number (e.g. FSSAI-NUTRA-LBL-101)\n"
            "- category: one of MANDATORY_FIELD | PROHIBITED_CLAIM | INGREDIENT_RESTRICTION | "
            "FORMAT_REQUIREMENT | QUANTITY_REQUIREMENT | WARNING | LICENSING\n"
            "- severity: CRITICAL | HIGH | MEDIUM | LOW\n"
            "- check_type: PRESENCE | ABSENCE | FORMAT | PATTERN_MATCH | VALUE_IN_LIST | NOT_IN_LIST\n"
            "- description: specific, checkable statement of the requirement (1-2 sentences)\n"
            "- regulation_source: exact section/clause citation\n"
            "- remediation_template: 1-sentence fix guidance\n"
            "- check_config: JSON object — for FORMAT: {\"description\": \"...\"}, "
            "for PRESENCE: {\"field\": \"field_name\"}, for PATTERN_MATCH: {\"field\": \"f\", \"pattern\": \"regex\"}\n"
            "- framework: FSSAI | LEGAL_METROLOGY | AYUSH | BIS | DGFT\n\n"
            "Only include requirements that are:\n"
            "1. Label-specific (appear on or relate to product packaging/labeling)\n"
            "2. Objectively testable (not subjective quality assessments)\n\n"
            "Return ONLY valid JSON, no markdown, no extra text:\n"
            "{\"rules\": [...]}"
        )

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)

        raw = response.text.strip()
        # Strip markdown code fences if present
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("{"):
                    raw = stripped
                    break

        data = _json.loads(raw)
        rules = data.get("rules", [])

        # Remove codes that already exist in the DB
        rules = [r for r in rules if r.get("rule_code") not in existing_codes]

        _EXTRACT_JOBS[job_id] = {
            "status": "done",
            "rules":  rules,
            "doc_title": doc_title,
        }
    except Exception as exc:
        _EXTRACT_JOBS[job_id] = {"status": "error", "error": str(exc)[:300]}


@router.post("/llm/regulations/extract-rules")
async def llm_extract_rules(request: Request, db: Session = Depends(get_db)):
    """Extract compliance rules from an indexed KB document using Gemini."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    import threading
    from app.models import KBDocument, KBType, ComplianceRule
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    doc_id = body.get("doc_id")
    if not doc_id:
        return JSONResponse({"error": "doc_id required"}, status_code=400)

    doc = db.query(KBDocument).filter(
        KBDocument.id == int(doc_id),
        KBDocument.kb_type == KBType.REGULATIONS,
        KBDocument.is_active,
    ).first()
    if not doc:
        return JSONResponse({"error": "Document not found"}, status_code=404)
    if not doc.content:
        return JSONResponse({"error": "Document has no content to analyze"}, status_code=400)

    existing_codes = {r.rule_code for r in db.query(ComplianceRule.rule_code).all()}

    job_id = str(uuid.uuid4())[:12]
    _EXTRACT_JOBS[job_id] = {"status": "processing", "note": "Starting…"}
    threading.Thread(
        target=_run_extract_job,
        args=(job_id, doc.content, doc.title or "Document", existing_codes),
        daemon=True,
    ).start()

    return JSONResponse({"job_id": job_id})


@router.get("/llm/regulations/extract-rules/status/{job_id}")
async def llm_extract_rules_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    job = _EXTRACT_JOBS.get(job_id)
    if not job:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return JSONResponse(job)


@router.post("/llm/regulations/approve-rules")
async def llm_approve_rules(request: Request, db: Session = Depends(get_db)):
    """Save admin-reviewed extracted rules into the compliance_rules table."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    import json as _json
    from app.models import ComplianceRule, RuleCategory, CheckType, Severity, RuleFramework
    from app.services.llm_service import invalidate_cache

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    rules = body.get("rules", [])
    if not rules:
        return JSONResponse({"error": "No rules provided"}, status_code=400)

    existing_codes = {r.rule_code for r in db.query(ComplianceRule.rule_code).all()}
    added, errors = 0, []

    for r in rules:
        try:
            code = (r.get("rule_code") or "").strip()
            if not code or code in existing_codes:
                continue

            try:
                category = RuleCategory(r.get("category", "MANDATORY_FIELD"))
            except ValueError:
                category = RuleCategory.MANDATORY_FIELD
            try:
                severity = Severity(r.get("severity", "MEDIUM"))
            except ValueError:
                severity = Severity.MEDIUM
            try:
                check_type = CheckType(r.get("check_type", "FORMAT"))
            except ValueError:
                check_type = CheckType.FORMAT
            try:
                framework = RuleFramework(r.get("framework", "FSSAI"))
            except ValueError:
                framework = RuleFramework.FSSAI

            cfg = r.get("check_config", {})
            if isinstance(cfg, str):
                try:
                    cfg = _json.loads(cfg)
                except Exception:
                    cfg = {}
            if not cfg:
                cfg = {"description": r.get("description", "")}

            db.add(ComplianceRule(
                rule_code=code,
                category=category,
                severity=severity,
                check_type=check_type,
                framework=framework,
                description=r.get("description", ""),
                regulation_source=r.get("regulation_source", ""),
                remediation_template=r.get("remediation_template", ""),
                check_config=cfg,
                active=True,
            ))
            existing_codes.add(code)
            added += 1
        except Exception as exc:
            errors.append(f"{r.get('rule_code', '?')}: {str(exc)[:80]}")

    db.commit()
    invalidate_cache("regulations")
    return JSONResponse({"added": added, "errors": errors, "message": f"Saved {added} new rule(s)."})


# ── KB Re-index job store ─────────────────────────────────────────────────────
_REINDEX_JOBS: dict = {}  # job_id → {status, progress, total, done, result}


def _run_reindex_job(job_id: str, kb_type: str):
    """Background thread: re-chunk all KB documents with improved chunker."""
    from app.database import SessionLocal
    from app.services.llm_service import reindex_kb
    db2 = SessionLocal()
    try:
        _REINDEX_JOBS[job_id]["status"] = "running"
        result = reindex_kb(db2, kb_type)
        _REINDEX_JOBS[job_id] = {
            "status": "done",
            **result,
        }
    except Exception as exc:
        _REINDEX_JOBS[job_id] = {
            "status": "error",
            "error": str(exc)[:300],
        }
    finally:
        db2.close()


@router.post("/llm/{kb_type}/reindex")
async def llm_reindex(kb_type: str, request: Request, db: Session = Depends(get_db)):
    """Start background re-chunking of all KB documents. Returns job_id for polling."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    if kb_type not in _VALID_KB:
        return JSONResponse({"error": "Invalid KB type"}, status_code=400)

    import threading
    job_id = str(uuid.uuid4())[:12]
    _REINDEX_JOBS[job_id] = {"status": "starting"}
    threading.Thread(
        target=_run_reindex_job,
        args=(job_id, kb_type),
        daemon=True,
    ).start()
    return JSONResponse({"job_id": job_id, "status": "starting"})


@router.get("/llm/{kb_type}/reindex/status/{job_id}")
async def llm_reindex_status(kb_type: str, job_id: str, request: Request,
                              db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    job = _REINDEX_JOBS.get(job_id)
    if not job:
        return JSONResponse({"status": "not_found"})
    return JSONResponse(job)


@router.post("/llm/{kb_type}/force-relearn")
async def llm_force_relearn(kb_type: str, request: Request, db: Session = Depends(get_db)):
    """
    Force re-read and re-chunk ALL uploaded PDF documents for this KB with the
    current (600-char) chunker. This is the same as Re-index but runs immediately
    in the foreground and returns stats — designed for the 'Re-read PDFs' flow.

    For each KBDocument:
      1. Deletes existing KBChunk rows
      2. Re-splits doc.content (stored extracted PDF text) with chunk_text(max_chars=600)
      3. Inserts new KBChunk rows

    Docs with < 20 chars of content are skipped (placeholder / empty records).
    """
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    if kb_type not in _VALID_KB:
        return JSONResponse({"error": "Invalid kb_type"}, status_code=400)

    import threading
    job_id = str(uuid.uuid4())[:12]
    _REINDEX_JOBS[job_id] = {"status": "starting"}
    threading.Thread(
        target=_run_reindex_job,
        args=(job_id, kb_type),
        daemon=True,
    ).start()
    return JSONResponse({"job_id": job_id, "status": "starting"})


@router.post("/llm/{kb_type}/documents/{doc_id}/delete")
async def llm_delete_document(
    kb_type: str, doc_id: int,
    request: Request, db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from app.models import KBDocument, KBType

    doc = db.query(KBDocument).filter(
        KBDocument.id == doc_id,
        KBDocument.kb_type == KBType(kb_type),
    ).first()

    if doc:
        db.delete(doc)   # cascade deletes KBChunk rows
        db.commit()
        msg = "Document+deleted"
        typ = "success"
    else:
        msg = "Document+not+found"
        typ = "error"

    return RedirectResponse(
        url=f"/admin/llm/{kb_type}/train?msg={msg}&type={typ}",
        status_code=302,
    )


# ── Chat test interface ───────────────────────────────────────────────────────

@router.get("/llm/{kb_type}/chat")
async def llm_chat_page(kb_type: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from app.services.llm_service import get_or_create_conversation, MODELS

    conv = get_or_create_conversation(kb_type, user.id, db)

    return templates.TemplateResponse("admin/llm_chat.html", {
        "request":       request,
        "user":          user,
        "unread_alerts": _unread_alerts(db),
        "kb_type":       kb_type,
        "messages":      conv.messages or [],
        "model_name":    MODELS.get(kb_type, "gemini-3.1-flash-lite-preview"),
    })


@router.post("/llm/{kb_type}/chat/send")
async def llm_chat_send(kb_type: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    if kb_type not in _VALID_KB:
        return JSONResponse({"error": "Invalid kb_type"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    user_message = (body.get("message") or "").strip()
    if not user_message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    from app.services.llm_service import ask_llm, get_or_create_conversation

    conv    = get_or_create_conversation(kb_type, user.id, db)
    history = conv.messages or []

    result  = ask_llm(kb_type, user_message, history, db)

    # Append both turns; keep last 40 messages to prevent unbounded growth
    conv.messages = (history + [
        {"role": "user",  "content": user_message},
        {"role": "model", "content": result["reply"]},
    ])[-40:]
    db.commit()

    return JSONResponse({
        "reply":        result["reply"],
        "context_used": result.get("context_used", []),
        "provider":     result.get("provider"),
        "error":        result.get("error"),
    })


# ── Label Extractor ──────────────────────────────────────────────────────────

@router.get("/label-extractor")
async def label_extractor_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from sqlalchemy import func
    from app.models import LabelVersion, ExtractionPattern
    from app.config import get_settings

    settings = get_settings()

    try:
        source_counts = (
            db.query(LabelVersion.extraction_source, func.count(LabelVersion.id))
            .filter(LabelVersion.extraction_source.isnot(None))
            .group_by(LabelVersion.extraction_source)
            .all()
        )
        source_stats = {s: c for s, c in source_counts}
    except Exception:
        source_stats = {}

    try:
        avg_conf = (
            db.query(LabelVersion.extraction_source, func.avg(LabelVersion.extraction_confidence))
            .filter(LabelVersion.extraction_source.isnot(None))
            .group_by(LabelVersion.extraction_source)
            .all()
        )
        conf_stats = {s: round(float(c or 0), 3) for s, c in avg_conf}
    except Exception:
        conf_stats = {}

    try:
        pattern_count = db.query(func.count(ExtractionPattern.id)).scalar() or 0
    except Exception:
        pattern_count = 0

    try:
        field_patterns = (
            db.query(ExtractionPattern.field_name, func.count(ExtractionPattern.id))
            .group_by(ExtractionPattern.field_name)
            .order_by(func.count(ExtractionPattern.id).desc())
            .limit(10)
            .all()
        )
    except Exception:
        field_patterns = []

    try:
        patterns_list = (
            db.query(ExtractionPattern)
            .order_by(ExtractionPattern.created_at.desc())
            .limit(300)
            .all()
        )
    except Exception:
        patterns_list = []

    return templates.TemplateResponse("admin/label_extractor.html", {
        "request":                  request,
        "user":                     user,
        "unread_alerts":            _unread_alerts(db),
        "source_stats":             source_stats,
        "conf_stats":               conf_stats,
        "pattern_count":            pattern_count,
        "field_patterns":           field_patterns,
        "gemini_model":             "gemini-3.1-flash-lite-preview",
        "claude_model":             "claude-sonnet-4-6",
        "gemini_available":         bool(settings.gemini_api_key),
        "claude_available":         bool(settings.anthropic_api_key),
        "local_enabled":            settings.local_extraction_enabled,
        "local_min_confidence":     settings.local_extraction_min_confidence,
        "patterns_list":            patterns_list,
    })


def _extract_pdf_content_for_kb(raw_bytes: bytes, filename: str) -> str:
    """Extract text from a PDF for KB ingestion.

    Priority:
    1. pdfplumber — fast, free, handles all digital/text PDFs (FSSAI regulations are always digital)
    2. Claude Vision — paid fallback for truly scanned/image-only PDFs (no text layer)

    NOTE: Gemma Vision is intentionally skipped here — regulation PDFs are digital text
    docs where pdfplumber excels. Gemma Vision is reserved for label image extraction
    and would cause unnecessary rate-limit (429) errors during bulk KB uploads.

    Returns extracted text (may be empty string if all fail).
    """
    import io
    import tempfile
    import os
    from app.config import get_settings
    cfg = get_settings()

    # ── Step 1: pdfplumber (fast, works for all digital PDFs) ─────────────
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
        text = "\n\n".join(pages).strip()
    except Exception:
        pass

    # Any reasonable text → use it immediately (regulation PDFs always have text)
    if len(text) > 50:
        return text[:50_000]  # cap at 50K chars for KB

    # ── Step 2: Claude Vision (scanned/image-only PDFs only) ──────────────
    # Only reached if pdfplumber found < 50 chars (truly image PDF, very rare for regulations)
    if cfg.anthropic_api_key:
        try:
            import os as _os
            _os.environ.setdefault("ANTHROPIC_API_KEY", cfg.anthropic_api_key)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            try:
                from app.services.extraction_service import _call_claude_vision
                result, _c_inp, _c_out = _call_claude_vision(tmp_path)
                if result:
                    lines = [f"{k}: {v}" for k, v in result.items() if v and not k.startswith("_")]
                    extracted = "\n".join(lines)
                    if len(extracted) > 50:
                        try:
                            from app.services.api_logger import log_api_call
                            log_api_call("kb_pdf_extract", "claude", "claude-sonnet-4-6", _c_inp, _c_out)
                        except Exception:
                            pass
                        return (text + "\n\n" + extracted).strip()[:50_000]
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        except Exception:
            pass

    return text  # return whatever pdfplumber got (may be empty)


def _run_benchmark_job(job_id: str, tmp_path: str, filename: str, file_size_kb: float):
    """Run all available providers on the same file, collect comparison stats."""
    import os
    from app.config import get_settings
    from app.services.extraction_service import (
        _normalize_extraction, _calculate_confidence,
        _call_claude_vision,
    )
    import time as _t

    cfg = get_settings()
    job = _BENCHMARK_JOBS[job_id]
    results = []

    def run_provider(name, step_label, fn, *args):
        start = _t.time()
        try:
            out = fn(*args)
            # fn returns (result_dict, inp_tokens, out_tokens)
            result_dict, inp, out_tok = out
            if result_dict:
                result_dict = _normalize_extraction(result_dict)
                confidence = _calculate_confidence(result_dict, "vision")
                field_count = sum(1 for v in result_dict.values() if v and not str(v).startswith('_'))
            else:
                confidence, field_count, inp, out_tok = 0.0, 0, inp, out_tok
            elapsed = round(_t.time() - start, 2)
            # cost
            RATES = {"gemma": (0.10, 0.40), "claude": (3.00, 15.00), "gemini": (0.075, 0.30)}
            src = name.lower().split()[0]
            r = RATES.get(src, (0, 0))
            cost = (inp / 1_000_000) * r[0] + (out_tok / 1_000_000) * r[1]
            results.append({
                "provider": name,
                "status": "success",
                "elapsed": elapsed,
                "confidence": round(confidence, 3),
                "field_count": field_count,
                "tokens_in": inp,
                "tokens_out": out_tok,
                "cost_usd": round(cost, 6),
                "error": None,
            })
        except Exception as e:
            elapsed = round(_t.time() - start, 2)
            results.append({
                "provider": name,
                "status": "error",
                "elapsed": elapsed,
                "confidence": 0.0,
                "field_count": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "error": str(e)[:120],
            })

    try:
        if cfg.anthropic_api_key:
            import os as _os
            _os.environ.setdefault("ANTHROPIC_API_KEY", cfg.anthropic_api_key)
            job["current"] = "Claude Vision…"
            run_provider("Claude Vision", "claude", _call_claude_vision, tmp_path)

        if cfg.gemini_api_key:
            job["current"] = "Gemini Vision…"
            try:
                from app.services.extraction_service import _call_gemini_vision
                start = _t.time()
                r = _call_gemini_vision(tmp_path)
                if r:
                    r = _normalize_extraction(r)
                    conf = _calculate_confidence(r, "vision")
                    fc = sum(1 for v in r.values() if v)
                else:
                    conf, fc = 0.0, 0
                elapsed = round(_t.time() - start, 2)
                results.append({"provider": "Gemini Vision", "status": "success", "elapsed": elapsed,
                    "confidence": round(conf, 3), "field_count": fc, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "error": None})
            except Exception as e:
                results.append({"provider": "Gemini Vision", "status": "error", "elapsed": 0, "confidence": 0,
                    "field_count": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "error": str(e)[:120]})

        job["done"] = True
        job["results"] = results
    except Exception as e:
        job["done"] = True
        job["error"] = str(e)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _run_extraction_job(job_id: str, tmp_path: str, filename: str, file_size_kb: float):
    """Run label extraction step-by-step, updating job state for live UI polling."""
    import os
    from app.config import get_settings
    from app.services.extraction_service import (
        _normalize_extraction, _calculate_confidence,
        _call_claude_vision, _call_claude_text,
    )

    cfg = get_settings()
    job = _EXTRACTION_JOBS[job_id]
    start = _time.time()

    def step(sid, label):
        job["step_id"] = sid
        job["step_label"] = label

    def finish(source, step_label, result_dict, inp, out):
        result_dict = _normalize_extraction(result_dict)
        confidence = _calculate_confidence(result_dict, "vision")
        warnings = result_dict.pop("_extraction_warnings", [])
        job["done"] = True
        job["result"] = {
            "source":        source,
            "source_step":   step_label,
            "confidence":    confidence,
            "elapsed_sec":   round(_time.time() - start, 2),
            "input_tokens":  inp,
            "output_tokens": out,
            "extraction":    result_dict,
            "warnings":      warnings,
            "filename":      filename,
            "file_size_kb":  file_size_kb,
        }

    try:
        # Step 0 — cache (we skip real cache in admin test mode)
        step("cache", "Checking cache…")
        _time.sleep(0.2)

        # Step 1 — OCR
        step("ocr", "Running OCR (Tesseract)…")
        ocr_text = ""
        try:
            from app.services.ocr_service import run_ocr
            ocr_text = run_ocr(tmp_path) or ""
        except Exception:
            pass

        # Step 1.5 — Local patterns
        step("local", "Checking local pattern library…")
        _time.sleep(0.1)

        # Step 2 — Claude Vision
        if cfg.anthropic_api_key:
            step("claude_vision", "Running Claude Vision (claude-sonnet-4-6)…")
            try:
                import os
                os.environ.setdefault("ANTHROPIC_API_KEY", cfg.anthropic_api_key)
                result, inp, out = _call_claude_vision(tmp_path)
                if result:
                    finish("claude", "Claude Vision", result, inp, out)
                    return
            except Exception as e:
                job["step_label"] = f"Claude Vision failed: {str(e)[:80]} — trying text…"
                _time.sleep(0.3)

        # Step 3 — Claude Text
        if cfg.anthropic_api_key and ocr_text:
            step("claude_text", "Running Claude Text…")
            try:
                result, inp, out = _call_claude_text(ocr_text)
                if result:
                    finish("claude", "Claude Text", result, inp, out)
                    return
            except Exception:
                pass

        # Step 4 — Gemini
        if cfg.gemini_api_key:
            step("gemini", "Running Gemini (gemini-3.1-flash-lite-preview)…")
            try:
                from app.services.extraction_service import _call_gemini_vision
                result = _call_gemini_vision(tmp_path)
                if result:
                    finish("gemini", "Gemini Vision", result, 0, 0)
                    return
            except Exception:
                pass

        # Step 5 — nothing worked
        step("done", "Extraction complete (fallback)")
        job["done"] = True
        job["result"] = {
            "source": "fallback", "source_step": "Rule-based fallback",
            "confidence": 0.0, "elapsed_sec": round(_time.time() - start, 2),
            "input_tokens": 0, "output_tokens": 0,
            "extraction": {}, "warnings": ["No AI provider succeeded"],
            "filename": filename, "file_size_kb": file_size_kb,
        }

    except Exception as e:
        job["done"] = True
        job["error"] = str(e)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/label-extractor/upload")
async def label_extractor_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    import tempfile
    job_id = str(uuid.uuid4())[:12]
    suffix = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    content = await file.read()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    _EXTRACTION_JOBS[job_id] = {
        "step_id":    "queued",
        "step_label": "Queued…",
        "done":       False,
        "result":     None,
        "error":      None,
        "started_at": _time.time(),
    }
    background_tasks.add_task(
        _run_extraction_job, job_id, tmp_path,
        file.filename or "upload", round(len(content) / 1024, 1)
    )
    return JSONResponse({"job_id": job_id})


@router.get("/label-extractor/job/{job_id}")
async def label_extractor_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    job = _EXTRACTION_JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    elapsed = round(_time.time() - job["started_at"], 1)

    if job["error"]:
        return JSONResponse({"done": True, "success": False, "error": job["error"], "elapsed_sec": elapsed})

    if job["done"] and job["result"]:
        return JSONResponse({"done": True, "success": True, "elapsed_sec": elapsed, **job["result"]})

    return JSONResponse({
        "done":        False,
        "step_id":     job["step_id"],
        "step_label":  job["step_label"],
        "elapsed_sec": elapsed,
    })


@router.post("/label-extractor/benchmark/start")
async def label_extractor_benchmark_start(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    import tempfile
    job_id = str(uuid.uuid4())[:12]
    suffix = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    _BENCHMARK_JOBS[job_id] = {
        "current": "Starting…", "done": False,
        "results": [], "error": None,
        "started_at": _time.time(),
        "filename": file.filename,
        "file_size_kb": round(len(content)/1024, 1),
    }
    background_tasks.add_task(_run_benchmark_job, job_id, tmp_path, file.filename or "upload", round(len(content)/1024, 1))
    return JSONResponse({"job_id": job_id})


@router.get("/label-extractor/benchmark/job/{job_id}")
async def label_extractor_benchmark_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)
    job = _BENCHMARK_JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "Not found"}, status_code=404)
    elapsed = round(_time.time() - job["started_at"], 1)
    if job["error"]:
        return JSONResponse({"done": True, "error": job["error"], "elapsed": elapsed})
    return JSONResponse({
        "done": job["done"],
        "current": job.get("current", "Running…"),
        "results": job["results"],
        "elapsed": elapsed,
        "filename": job.get("filename"),
        "file_size_kb": job.get("file_size_kb"),
    })


@router.post("/llm/{kb_type}/chat/clear")
async def llm_chat_clear(kb_type: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Not authorised"}, status_code=401)

    from app.services.llm_service import get_or_create_conversation

    conv = get_or_create_conversation(kb_type, user.id, db)
    conv.messages = []
    db.commit()

    return JSONResponse({"status": "cleared"})


# ── Compliance Coverage Dashboard ─────────────────────────────────────────────

@router.get("/compliance/coverage")
async def compliance_coverage(request: Request, db: Session = Depends(get_db)):
    """
    Live compliance audit dashboard — shows rule health, extraction coverage,
    regulation sync status, product scan coverage and KB health in one page.
    """
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    from datetime import datetime, timedelta
    from collections import defaultdict

    from app.models import (
        ComplianceRule, CheckType, RuleFramework, Severity,
        RegulationChange, Product, LabelVersion, ComplianceCheck, CheckResult,
        KBDocument, KBChunk, KBType,
    )
    from app.config import get_settings as _cfg
    from app.services.extraction_service import ALL_EXPECTED_FIELDS

    cfg = _cfg()

    # ── 1. Rule summary ───────────────────────────────────────────────────────
    all_rules  = db.query(ComplianceRule).all()
    active     = [r for r in all_rules if r.active]

    by_framework: dict[str, int] = defaultdict(int)
    by_check_type: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)
    format_llm_rules: list[ComplianceRule] = []

    for r in active:
        fw  = r.framework.value if r.framework else "UNKNOWN"
        ct  = r.check_type.value if r.check_type else "UNKNOWN"
        sev = r.severity.value if r.severity else "UNKNOWN"
        by_framework[fw]  += 1
        by_check_type[ct] += 1
        by_severity[sev]  += 1
        if ct == "FORMAT_LLM":
            format_llm_rules.append(r)

    rule_summary = {
        "total":        len(all_rules),
        "active":       len(active),
        "inactive":     len(all_rules) - len(active),
        "by_framework": dict(by_framework),
        "by_check_type": dict(by_check_type),
        "by_severity":  dict(by_severity),
    }

    # ── 2. FORMAT_LLM health ─────────────────────────────────────────────────
    gemini_available = bool(cfg.gemini_api_key)
    claude_available = bool(cfg.anthropic_api_key)
    format_llm_health = {
        "rules_at_risk":    len(format_llm_rules),
        "gemini_available": gemini_available,
        "claude_available": claude_available,
        "any_llm_available": gemini_available or claude_available,
        "rule_codes":       [r.rule_code for r in format_llm_rules[:20]],
    }

    # ── 3. Extraction coverage ────────────────────────────────────────────────
    # Collect all fields that at least one active rule actually checks
    fields_with_rules: set[str] = set()
    for r in active:
        cfg_field = (r.check_config or {}).get("field")
        if cfg_field:
            fields_with_rules.add(cfg_field)

    all_extracted = set(ALL_EXPECTED_FIELDS)
    fields_no_rules = sorted(all_extracted - fields_with_rules)

    extraction_coverage = {
        "total_extracted_fields":    len(all_extracted),
        "fields_with_rules":         len(fields_with_rules),
        "fields_extracted_no_rules": fields_no_rules,
        "rules_with_no_extractor":   [],  # could cross-check if needed
    }

    # ── 4. Regulation sync status ─────────────────────────────────────────────
    total_changes = db.query(RegulationChange).count()
    empty_affected = db.query(RegulationChange).filter(
        # JSON column: empty list or null
        (RegulationChange.affected_rule_codes == None)  # noqa: E711
        | (RegulationChange.affected_rule_codes == [])
    ).count()

    last_change = (
        db.query(RegulationChange)
        .order_by(RegulationChange.detected_at.desc())
        .first()
    )

    regulation_sync = {
        "total_regulation_changes":         total_changes,
        "changes_with_empty_affected_codes": empty_affected,
        "pct_with_affected_codes":          (
            round(100 * (total_changes - empty_affected) / total_changes, 1)
            if total_changes else 0
        ),
        "last_scrape": last_change.detected_at.isoformat() if last_change else None,
    }

    # ── 5. Product scan coverage ──────────────────────────────────────────────
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    active_products = (
        db.query(Product)
        .filter(Product.is_active == True, Product.is_quick_check == False)
        .all()
    )
    total_products = len(active_products)

    # Products with at least one compliance check in the last 30 days
    scanned_ids = {
        row[0]
        for row in (
            db.query(LabelVersion.product_id)
            .join(ComplianceCheck, LabelVersion.id == ComplianceCheck.label_version_id)
            .filter(
                LabelVersion.is_current == True,
                ComplianceCheck.checked_at >= thirty_days_ago,
            )
            .distinct()
            .all()
        )
    }
    never_scanned_ids = {
        p.id for p in active_products
        if not db.query(ComplianceCheck)
               .join(LabelVersion, ComplianceCheck.label_version_id == LabelVersion.id)
               .filter(LabelVersion.product_id == p.id)
               .first()
    }

    # Average compliance score across current labels
    scores: list[float] = []
    failing_critical = 0
    for product in active_products:
        current = (
            db.query(LabelVersion)
            .filter(LabelVersion.product_id == product.id, LabelVersion.is_current == True)
            .first()
        )
        if current and current.compliance_score is not None:
            scores.append(current.compliance_score)
        # Count products with at least one CRITICAL FAIL
        has_critical_fail = (
            db.query(ComplianceCheck)
            .join(ComplianceRule, ComplianceCheck.rule_id == ComplianceRule.id)
            .join(LabelVersion, ComplianceCheck.label_version_id == LabelVersion.id)
            .filter(
                LabelVersion.product_id == product.id,
                LabelVersion.is_current == True,
                ComplianceCheck.result == CheckResult.FAIL,
                ComplianceRule.severity == Severity.CRITICAL,
            )
            .first()
        )
        if has_critical_fail:
            failing_critical += 1

    product_scan = {
        "total_active_products":  total_products,
        "scanned_last_30_days":   len(scanned_ids),
        "never_scanned":          len(never_scanned_ids),
        "never_scanned_pct":      round(100 * len(never_scanned_ids) / total_products, 1) if total_products else 0,
        "avg_score":              round(sum(scores) / len(scores), 1) if scores else None,
        "failing_critical":       failing_critical,
    }

    # ── 6. KB health ─────────────────────────────────────────────────────────
    def _kb_stats(kb_type_val: KBType) -> dict:
        docs = (
            db.query(KBDocument)
            .filter(KBDocument.kb_type == kb_type_val, KBDocument.is_active == True)
            .all()
        )
        chunks = db.query(KBChunk).join(
            KBDocument, KBChunk.document_id == KBDocument.id
        ).filter(KBDocument.kb_type == kb_type_val, KBDocument.is_active == True).count()

        oldest_days = None
        if docs:
            oldest = min(d.uploaded_at for d in docs)
            oldest_days = (datetime.utcnow() - oldest).days

        return {
            "doc_count":   len(docs),
            "chunk_count": chunks,
            "oldest_days": oldest_days,
        }

    kb_health = {
        "regulations": _kb_stats(KBType.REGULATIONS),
        "products":    _kb_stats(KBType.PRODUCTS),
    }

    return templates.TemplateResponse("admin/compliance_coverage.html", {
        "request":            request,
        "user":               user,
        "unread_alerts":      _unread_alerts(db),
        "rule_summary":       rule_summary,
        "format_llm_health":  format_llm_health,
        "extraction_coverage": extraction_coverage,
        "regulation_sync":    regulation_sync,
        "product_scan":       product_scan,
        "kb_health":          kb_health,
        "generated_at":       datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    })
