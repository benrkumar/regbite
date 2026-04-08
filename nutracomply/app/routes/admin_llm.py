"""
LLM Studio — Admin routes
=========================
All routes require is_admin=True.
Provides knowledge-base management (train) and chat test interfaces for
the Regulations LLM (gemini-2.5-pro) and Products LLM (gemini-2.0-flash),
with Claude (Anthropic) as automatic fallback.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie

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
            result["gemma"] = {"status": "error", "error": str(exc)[:300], "model": settings.gemma_model_name}
    else:
        result["gemma"] = {"status": "not_configured"}

    # ── Test Claude ───────────────────────────────────────────────────────────
    if settings.anthropic_api_key:
        try:
            import anthropic as _ant
            client = _ant.Anthropic(api_key=settings.anthropic_api_key)
            client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=5,
                messages=[{"role": "user", "content": "Reply: OK"}],
            )
            result["claude"] = {"status": "ok"}
        except Exception as exc:
            result["claude"] = {"status": "error", "error": str(exc)[:200]}
    else:
        result["claude"] = {"status": "not_configured"}

    # ── Test Gemini ───────────────────────────────────────────────────────────
    if settings.gemini_api_key:
        try:
            import google.generativeai as _genai
            _genai.configure(api_key=settings.gemini_api_key)
            m = _genai.GenerativeModel("gemini-2.5-flash-preview-04-17")
            m.generate_content("Reply: OK", generation_config={"max_output_tokens": 5})
            result["gemini"] = {"status": "ok"}
        except Exception as exc:
            result["gemini"] = {"status": "error", "error": str(exc)[:200]}
    else:
        result["gemini"] = {"status": "not_configured"}

    return JSONResponse(result)


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
                KBDocument.is_active == True)
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
            .filter(ComplianceRule.active == True)
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

    from app.services.llm_service import seed_regulations_kb, seed_products_kb

    try:
        if kb_type == "regulations":
            result = seed_regulations_kb(db)
        else:
            result = seed_products_kb(db)

        if result["status"] == "up_to_date":
            msg  = f"Knowledge+base+already+seeded+({result['document_count']}+documents+exist)"
            typ  = "info"
        else:
            msg  = f"Seeded+{result['document_count']}+documents+from+database"
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
    Inserts any new rules that don't already exist. Never deletes existing data."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    import json
    from pathlib import Path as _Path
    from app.models import ComplianceRule as _ComplianceRule

    rules_path = _Path(__file__).parent.parent / "data" / "fssai_rules_seed.json"
    try:
        with open(rules_path, encoding="utf-8") as f:
            rules_data = json.load(f)

        existing_codes = {r.rule_code for r in db.query(_ComplianceRule.rule_code).all()}
        new_rules = [r for r in rules_data if r["rule_code"] not in existing_codes]

        if new_rules:
            for r in new_rules:
                db.add(_ComplianceRule(**r))
            db.commit()

        msg = f"Synced+{len(new_rules)}+new+rules.+Total:+{len(existing_codes)+len(new_rules)}+rules+in+database."
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
    Selectively delete + re-seed a subset of the regulations KB.
    subset param: "all" | "fssai" | "ayush" | "legal_metrology"
    """
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from sqlalchemy import or_
    from app.models import KBDocument, KBChunk, KBType
    from app.services.llm_service import seed_regulations_kb, seed_products_kb, invalidate_cache

    form   = await request.form()
    subset = form.get("subset", "all")  # "all" | "fssai" | "ayush" | "legal_metrology"

    try:
        if kb_type != "regulations" or subset == "all":
            # Full wipe for products KB or explicit "all"
            deleted_chunks = db.query(KBChunk).filter(
                KBChunk.kb_type == KBType(kb_type)).delete(synchronize_session=False)
            deleted_docs = db.query(KBDocument).filter(
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
            deleted_chunks = 0
            deleted_docs   = 0
            if matching_doc_ids:
                deleted_chunks = db.query(KBChunk).filter(
                    KBChunk.document_id.in_(matching_doc_ids)
                ).delete(synchronize_session=False)
                deleted_docs = db.query(KBDocument).filter(
                    KBDocument.id.in_(matching_doc_ids)
                ).delete(synchronize_session=False)
            db.commit()

        invalidate_cache(kb_type)

        # Re-seed the same subset from DB
        if kb_type == "regulations":
            fw = None if subset == "all" else subset
            result = seed_regulations_kb(db, framework=fw)
        else:
            result = seed_products_kb(db)

        label = {"fssai": "FSSAI", "ayush": "AYUSH",
                 "legal_metrology": "Legal+Metrology", "all": "All"}.get(subset, subset)
        msg = (
            f"Reset+{label}:+deleted+{deleted_docs}+docs+{deleted_chunks}+chunks."
            f"+Re-seeded+{result['new_documents']}+documents+from+DB."
        )
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
            msg = f"No+PDF+files+found+in+FSSAI+folder"
            typ = "warning"
    except Exception as exc:
        msg = f"FSSAI+ingest+failed:+{str(exc)[:120].replace(' ', '+')}"
        typ = "error"

    return RedirectResponse(
        url=f"/admin/llm/regulations/train?msg={msg}&type={typ}",
        status_code=302,
    )


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
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from app.services.llm_service import _ingest_document

    try:
        filename = file.filename or "upload"
        display_title = title.strip() or filename
        raw_bytes = await file.read()

        if not raw_bytes:
            raise ValueError("File is empty")

        if filename.lower().endswith(".pdf"):
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                content = "\n\n".join(
                    (page.extract_text() or "") for page in pdf.pages
                )
        else:
            content = raw_bytes.decode("utf-8", errors="replace")

        content = content.strip()
        if not content:
            raise ValueError("File appears to be empty or unreadable after extraction")

        doc = _ingest_document(
            db, kb_type,
            title=display_title,
            source=f"upload:{filename}",
            content=content,
            uploaded_by_id=user.id,
        )
        msg = f"Uploaded+and+indexed+{doc.chunk_count}+chunks+from+{filename.replace(' ', '+')}"
        typ = "success"

    except Exception as exc:
        msg = f"Upload+failed:+{str(exc)[:120].replace(' ', '+')}"
        typ = "error"

    return RedirectResponse(
        url=f"/admin/llm/{kb_type}/train?msg={msg}&type={typ}",
        status_code=302,
    )


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
        "model_name":    MODELS.get(kb_type, "gemini-2.0-flash"),
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
