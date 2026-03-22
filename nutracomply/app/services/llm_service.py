"""
LLM Studio — RAG service layer
================================
Two knowledge bases (Regulations + Products), each backed by Gemini via
Retrieval-Augmented Generation.  Retrieval uses PostgreSQL LIKE-based
full-text scoring — no pgvector required.

Models used:
  regulations → gemini-1.5-pro   (precision for legal/regulatory reasoning)
  products    → gemini-2.0-flash  (fast for structured product/label data)
"""
from __future__ import annotations

# ─── Per-KB Gemini model names ────────────────────────────────────────────────

MODELS: dict[str, str] = {
    "regulations": "gemini-1.5-pro",
    "products":    "gemini-2.0-flash",
}

# ─── System prompts ───────────────────────────────────────────────────────────

SYSTEM_PROMPTS: dict[str, str] = {
    "regulations": (
        "You are RegBite's Regulatory Compliance Expert for India. "
        "Your knowledge base covers three regulatory frameworks: "
        "(1) FSSAI — Food Safety and Standards Authority of India regulations for health supplements, "
        "nutraceuticals, food labelling, and ingredient restrictions; "
        "(2) Legal Metrology — Packaged Commodities Rules 2011 covering MRP, net quantity, "
        "manufacturer details, bilingual declarations, and consumer care requirements; "
        "(3) AYUSH — Ayurvedic, Siddha, and Unani (ASU) drug regulations under the Drugs and Cosmetics Act 1940 "
        "covering formulation labelling, Schedule E(1) restricted ingredients, Bhasma/Rasa metal content, "
        "and the Drugs and Magic Remedies Act prohibitions. "
        "Answer questions accurately using ONLY the provided context. "
        "Always cite the relevant rule code or regulation source when available. "
        "If the context does not contain enough information, say so clearly — "
        "do not hallucinate rule details."
    ),
    "products": (
        "You are RegBite's Product Compliance Analyst. "
        "Your knowledge base contains product data, label analysis results, "
        "and compliance check outcomes for nutraceutical, health supplement, and AYUSH products "
        "on the RegBite platform. Products are checked against FSSAI, Legal Metrology, "
        "and AYUSH regulations. "
        "Answer questions about specific products, their compliance scores, "
        "failing checks, and remediation steps. "
        "Keep responses factual and reference product names or SKUs when available."
    ),
}


# ─── Text chunking ────────────────────────────────────────────────────────────

def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    """
    Split *text* into chunks of at most *max_chars* characters.
    Splits on paragraph boundaries first (double newlines), then on word
    boundaries for paragraphs that exceed the limit.
    Returns a list of non-empty, stripped strings.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            words = para.split()
            current: list[str] = []
            current_len = 0
            for word in words:
                if current_len + len(word) + 1 > max_chars and current:
                    chunks.append(" ".join(current))
                    current = [word]
                    current_len = len(word)
                else:
                    current.append(word)
                    current_len += len(word) + 1
            if current:
                chunks.append(" ".join(current))

    return [c for c in chunks if c]


# ─── Document ingestion ───────────────────────────────────────────────────────

def _ingest_document(db, kb_type: str, title: str, source: str,
                     content: str, uploaded_by_id: int | None = None):
    """
    Create a KBDocument, chunk its content, insert KBChunk rows, and commit.
    Returns the created KBDocument.
    """
    from app.models import KBDocument, KBChunk, KBType

    doc = KBDocument(
        kb_type=KBType(kb_type),
        title=title,
        source=source,
        content=content,
        uploaded_by=uploaded_by_id,
    )
    db.add(doc)
    db.flush()  # get doc.id without committing transaction

    chunks = chunk_text(content)
    for i, chunk_content in enumerate(chunks):
        db.add(KBChunk(
            document_id=doc.id,
            kb_type=KBType(kb_type),
            chunk_index=i,
            content=chunk_content,
        ))

    doc.chunk_count = len(chunks)
    db.commit()
    return doc


# ─── KB seeding from DB ───────────────────────────────────────────────────────

def seed_regulations_kb(db) -> dict:
    """
    Auto-populate the Regulations knowledge base from existing DB rows.
    Additive — only inserts documents whose source doesn't already exist.
    Data is permanently stored and never auto-deleted.
    Sources: ComplianceRule, RegulationChange, Ingredient.
    """
    from app.models import KBDocument, KBType, ComplianceRule, RegulationChange, Ingredient

    # Get existing sources to avoid duplicates
    existing_sources = {
        d.source for d in
        db.query(KBDocument.source).filter(
            KBDocument.kb_type == KBType.REGULATIONS,
            KBDocument.is_active == True,
        ).all()
    }

    count = 0

    # ── Compliance Rules ──────────────────────────────────────────────────────
    for rule in db.query(ComplianceRule).filter(ComplianceRule.active == True).all():
        source = f"db:compliance_rule:{rule.id}"
        if source in existing_sources:
            continue
        content = (
            f"Compliance Rule: {rule.rule_code}\n"
            f"Category: {rule.category.value}\n"
            f"Regulation Source: {rule.regulation_source or 'N/A'}\n"
            f"Severity: {rule.severity.value}\n"
            f"Description: {rule.description}\n"
            f"Check Type: {rule.check_type.value}\n"
            f"Remediation: {rule.remediation_template or 'N/A'}"
        )
        _ingest_document(
            db, "regulations",
            title=f"Rule {rule.rule_code}: {rule.description[:70]}",
            source=f"db:compliance_rule:{rule.id}",
            content=content,
        )
        count += 1

    # ── Regulation Changes ────────────────────────────────────────────────────
    for change in db.query(RegulationChange).all():
        source = f"db:regulation_change:{change.id}"
        if source in existing_sources:
            continue
        eff = change.effective_date.strftime("%Y-%m-%d") if change.effective_date else "TBD"
        content = (
            f"Regulation Update: {change.document_name or 'Unnamed'}\n"
            f"Change Type: {change.change_type.value}\n"
            f"Detected: {change.detected_at.strftime('%Y-%m-%d')}\n"
            f"Effective Date: {eff}\n"
            f"Severity: {change.severity.value}\n"
            f"Summary: {change.summary_text or 'N/A'}\n"
            f"Affected Rules: {', '.join(change.affected_rule_codes or [])}\n"
            f"Source URL: {change.source_url or 'N/A'}"
        )
        _ingest_document(
            db, "regulations",
            title=f"Reg Change: {(change.document_name or 'Update')[:70]}",
            source=source,
            content=content,
        )
        count += 1

    # ── Ingredients ───────────────────────────────────────────────────────────
    for ing in db.query(Ingredient).all():
        source = f"db:ingredient:{ing.id}"
        if source in existing_sources:
            continue
        content = (
            f"Ingredient: {ing.name}\n"
            f"Status: {ing.status.value}\n"
            f"Aliases: {', '.join(ing.aliases or [])}\n"
            f"Max Daily Dose: {ing.max_daily_dose or 'N/A'}\n"
            f"Source Restriction: {ing.source_restriction or 'None'}\n"
            f"Ban Reason: {ing.ban_reason or 'N/A'}\n"
            f"Regulation Reference: {ing.regulation_reference or 'N/A'}"
        )
        _ingest_document(
            db, "regulations",
            title=f"Ingredient: {ing.name}",
            source=source,
            content=content,
        )
        count += 1

    total = len(existing_sources) + count
    return {"status": "seeded" if count > 0 else "up_to_date", "document_count": total, "new_documents": count}


def seed_products_kb(db) -> dict:
    """
    Auto-populate the Products knowledge base from existing DB rows.
    Additive — only inserts products whose source doesn't already exist.
    Data is permanently stored and never auto-deleted.
    Sources: Product + latest LabelVersion + ComplianceCheck failures.
    """
    from app.models import KBDocument, KBType, Product, LabelVersion, ComplianceCheck, ComplianceRule, CheckResult

    existing_sources = {
        d.source for d in
        db.query(KBDocument.source).filter(
            KBDocument.kb_type == KBType.PRODUCTS,
            KBDocument.is_active == True,
        ).all()
    }

    count = 0

    for product in db.query(Product).filter(Product.is_active == True).all():
        source = f"db:product:{product.id}"
        if source in existing_sources:
            continue
        latest_lv = (
            db.query(LabelVersion)
            .filter(LabelVersion.product_id == product.id,
                    LabelVersion.is_current == True)
            .first()
        )

        checks_summary = ""
        if latest_lv:
            checks = (
                db.query(ComplianceCheck)
                .filter(ComplianceCheck.label_version_id == latest_lv.id)
                .all()
            )
            total  = len(checks)
            passed = sum(1 for c in checks if c.result == CheckResult.PASS)
            failed = [c for c in checks if c.result == CheckResult.FAIL]

            fail_lines = []
            for fc in failed[:10]:
                rule = db.query(ComplianceRule).filter(
                    ComplianceRule.id == fc.rule_id
                ).first()
                rule_code = rule.rule_code if rule else "Unknown"
                fail_lines.append(f"  - FAIL [{rule_code}]: {fc.message or 'No detail'}")

            score = round((passed / total) * 100) if total else 0
            checks_summary = (
                f"\nLabel Analysis (uploaded {latest_lv.uploaded_at.strftime('%Y-%m-%d')}):\n"
                f"Compliance Score: {score}% ({passed}/{total} checks passed)\n"
                f"Failing Checks:\n"
                + ("\n".join(fail_lines) if fail_lines else "  None")
                + f"\nOCR Text Preview: {(latest_lv.ocr_raw_text or '')[:400]}"
            )

        content = (
            f"Product: {product.name}\n"
            f"SKU: {product.sku or 'N/A'}\n"
            f"Category: {product.category or 'Nutraceutical'}\n"
            f"Description: {product.description or 'N/A'}\n"
            f"Created: {product.created_at.strftime('%Y-%m-%d')}"
            + checks_summary
        )

        _ingest_document(
            db, "products",
            title=f"Product: {product.name}",
            source=source,
            content=content,
        )
        count += 1

    total = len(existing_sources) + count
    return {"status": "seeded" if count > 0 else "up_to_date", "document_count": total, "new_documents": count}


# ─── Context retrieval ────────────────────────────────────────────────────────

def retrieve_context(kb_type: str, query: str, db, top_k: int = 8) -> list[dict]:
    """
    Search kb_chunks for the most relevant chunks matching *query* using
    LIKE-based multi-word scoring.  No pgvector required.

    Returns a list of dicts: {"chunk_id", "content", "document_title"}.
    """
    from app.models import KBChunk, KBDocument, KBType
    from sqlalchemy import or_, case

    # Tokenize: keep words ≥ 3 chars, cap at 8 terms
    words = [w.strip().lower() for w in query.split() if len(w.strip()) >= 3][:8]

    if not words:
        # Fallback: return most recently added chunks
        rows = (
            db.query(KBChunk)
            .join(KBDocument, KBChunk.document_id == KBDocument.id)
            .filter(KBChunk.kb_type == KBType(kb_type),
                    KBDocument.is_active == True)
            .order_by(KBChunk.id.desc())
            .limit(top_k)
            .all()
        )
        return [
            {"chunk_id": c.id, "content": c.content,
             "document_title": c.document.title if c.document else "Unknown"}
            for c in rows
        ]

    # Build score expression: sum of per-word CASE expressions
    # Using + (not Python sum()) because SQLAlchemy 2.x doesn't support sum() over column exprs
    score = case((KBChunk.content.ilike(f"%{words[0]}%"), 1), else_=0)
    for word in words[1:]:
        score = score + case((KBChunk.content.ilike(f"%{word}%"), 1), else_=0)

    or_conditions = or_(*[KBChunk.content.ilike(f"%{w}%") for w in words])

    results = (
        db.query(KBChunk, score.label("score"))
        .join(KBDocument, KBChunk.document_id == KBDocument.id)
        .filter(
            KBChunk.kb_type == KBType(kb_type),
            KBDocument.is_active == True,
            or_conditions,
        )
        .order_by(score.desc(), KBChunk.id)
        .limit(top_k)
        .all()
    )

    return [
        {
            "chunk_id": row.KBChunk.id,
            "content":  row.KBChunk.content,
            "document_title": (
                row.KBChunk.document.title if row.KBChunk.document else "Unknown"
            ),
        }
        for row in results
    ]


# ─── Gemini call ──────────────────────────────────────────────────────────────

def ask_llm(kb_type: str, query: str, history: list, db) -> dict:
    """
    RAG pipeline: retrieve context → build prompt → call Gemini.

    Args:
        kb_type:  "regulations" or "products"
        query:    current user message
        history:  list of {"role":"user"|"model", "content":"..."} dicts
        db:       SQLAlchemy session

    Returns:
        {"reply": str, "context_used": [document_title, ...]}
        On error: {"reply": error_msg, "context_used": [], "error": error_code}
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.gemini_api_key:
        return {
            "reply": (
                "⚠️ Gemini API key is not configured. "
                "Please set GEMINI_API_KEY in your Railway environment variables."
            ),
            "context_used": [],
            "error": "no_api_key",
        }

    # Retrieve relevant chunks
    context_chunks = retrieve_context(kb_type, query, db, top_k=8)
    context_text = "\n\n---\n\n".join(
        f"[Source: {c['document_title']}]\n{c['content']}"
        for c in context_chunks
    )

    system_prompt = SYSTEM_PROMPTS.get(kb_type, SYSTEM_PROMPTS["regulations"])
    model_name    = MODELS.get(kb_type, "gemini-2.0-flash")

    # Full prompt: system instruction + retrieved context + user question
    full_prompt = (
        f"{system_prompt}\n\n"
        f"KNOWLEDGE BASE CONTEXT (use this to answer):\n"
        f"{context_text if context_text else '[No relevant context found in knowledge base]'}\n\n"
        f"USER QUESTION: {query}"
    )

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(model_name)

        # Build Gemini history from last 10 turns (roles: "user" / "model")
        gemini_history = [
            {"role": msg["role"], "parts": [msg["content"]]}
            for msg in history[-10:]
        ]

        chat     = model.start_chat(history=gemini_history)
        response = chat.send_message(
            full_prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": 1024},
        )
        reply = response.text.strip()

    except Exception as exc:
        reply = f"Error calling Gemini API ({model_name}): {str(exc)[:300]}"
        return {"reply": reply, "context_used": [], "error": "api_error"}

    return {
        "reply":        reply,
        "context_used": [c["document_title"] for c in context_chunks],
    }


# ─── Conversation helpers ─────────────────────────────────────────────────────

def get_or_create_conversation(kb_type: str, admin_id: int, db):
    """
    Return the most recent LLMConversation for this (admin, kb_type) pair,
    creating a fresh one if none exists.
    """
    from app.models import LLMConversation, KBType

    conv = (
        db.query(LLMConversation)
        .filter(
            LLMConversation.kb_type == KBType(kb_type),
            LLMConversation.admin_id == admin_id,
        )
        .order_by(LLMConversation.updated_at.desc())
        .first()
    )
    if not conv:
        conv = LLMConversation(
            kb_type=KBType(kb_type),
            admin_id=admin_id,
            messages=[],
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def get_kb_stats(kb_type: str, db) -> dict:
    """Return document and chunk counts for a given KB type."""
    from app.models import KBDocument, KBChunk, KBType

    doc_count   = db.query(KBDocument).filter(
        KBDocument.kb_type == KBType(kb_type),
        KBDocument.is_active == True,
    ).count()
    chunk_count = db.query(KBChunk).filter(
        KBChunk.kb_type == KBType(kb_type),
    ).count()
    return {"documents": doc_count, "chunks": chunk_count}
