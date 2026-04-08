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
        "request":           request,
        "user":              user,
        "unread_alerts":     _unread_alerts(db),
        "reg_stats":         reg_stats,
        "prod_stats":        prod_stats,
        "gemini_configured": bool(settings.gemini_api_key),
        "claude_configured": bool(settings.anthropic_api_key),
    })


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

    return templates.TemplateResponse("admin/llm_train.html", {
        "request":       request,
        "user":          user,
        "unread_alerts": _unread_alerts(db),
        "kb_type":       kb_type,
        "documents":     documents,
        "stats":         stats,
        "flash_message": flash_message or None,
        "flash_type":    flash_type,
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


@router.post("/llm/{kb_type}/reset")
async def llm_reset_kb(kb_type: str, request: Request, db: Session = Depends(get_db)):
    """Delete ALL documents + chunks for this KB, then re-seed from DB."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    if kb_type not in _VALID_KB:
        return RedirectResponse(url="/admin/llm", status_code=302)

    from app.models import KBDocument, KBChunk, KBType
    from app.services.llm_service import seed_regulations_kb, seed_products_kb, invalidate_cache

    try:
        # Hard-delete all chunks and documents for this KB
        deleted_chunks = db.query(KBChunk).filter(KBChunk.kb_type == KBType(kb_type)).delete()
        deleted_docs   = db.query(KBDocument).filter(KBDocument.kb_type == KBType(kb_type)).delete()
        db.commit()
        invalidate_cache(kb_type)

        # Re-seed from DB immediately
        if kb_type == "regulations":
            result = seed_regulations_kb(db)
        else:
            result = seed_products_kb(db)

        msg = (
            f"Reset+complete:+deleted+{deleted_docs}+docs+{deleted_chunks}+chunks."
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
