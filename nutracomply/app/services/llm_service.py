"""
LLM Studio — RAG service layer
================================
Two knowledge bases (Regulations + Products), each backed by Gemini via
Retrieval-Augmented Generation with Claude (Anthropic) as automatic fallback.

Retrieval uses PostgreSQL LIKE-based full-text scoring with stopword filtering
and title boosting — no pgvector required.

v3 improvements:
  - Stable Gemini model names (gemini-2.5-pro, gemini-3.1-flash-lite-preview)
  - Claude fallback: if Gemini API fails, automatically retries with Anthropic
  - Better error reporting surfaced to the chat UI

v4 improvements:
  - Fixed Claude model name: claude-sonnet-4-6 (was invalid claude-sonnet-4-20250514)
  - STOPWORDS no longer strips "not", "is", "for", "about", "why" — critical regulatory terms
  - chunk_text max_chars: 800 → 1200 (avoids mid-sentence cuts in long rule descriptions)
  - retrieve_context top_k: 10 → 15 (more context for multi-rule queries)
  - Anti-hallucination guardrails in both system prompts (no invented rule codes)

v5 improvements:
  - In-memory query result cache (TTL=1 hour, up to 500 entries) — avoids redundant LLM calls
  - Query expansion: short queries (< 6 meaningful words) expanded via Gemini Flash for better retrieval
  - Chunk-level deduplication in _ingest_document — skips exact-duplicate chunks
  - seed_products_kb supports force_update_product_id for targeted re-ingest
  - Phrase-level matching boost in retrieve_context (+3 per bigram match)
  - _build_context merges expanded + original query results for broader coverage
  - ask_llm checks cache before calling LLM; stores successful results in cache
  - History window increased: 10 → 20 turns for both Gemini and Claude
  - Citation format improved: includes section/clause and Sources used section
  - Auto-reseed hook in labels.py refreshes Products KB after each label scan

Models used:
  regulations → gemini-2.5-pro (precision for legal/regulatory reasoning)
  products    → gemini-3.1-flash-lite-preview (fast for structured product/label data)
  fallback    → claude-sonnet-4-6 (Anthropic) when Gemini unavailable
"""
from __future__ import annotations

import logging
import time
import hashlib
import warnings

# google-generativeai 0.8.x is deprecated in favour of google-genai; suppress the
# FutureWarning it emits on every import until we migrate.
warnings.filterwarnings("ignore", message=".*google.generativeai.*", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="google.generativeai")

logger = logging.getLogger(__name__)

# ─── In-memory query result cache (TTL = 1 hour) ─────────────────────────────
_QUERY_CACHE: dict = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def _cache_key(kb_type: str, query: str) -> str:
    return hashlib.md5(f"{kb_type}:{query.lower().strip()}".encode()).hexdigest()


def _get_cached(kb_type: str, query: str):
    """Return cached result if still within TTL, else None."""
    key = _cache_key(kb_type, query)
    entry = _QUERY_CACHE.get(key)
    if entry:
        result, ts = entry
        if time.time() - ts < CACHE_TTL_SECONDS:
            return result
        del _QUERY_CACHE[key]
    return None


def _set_cache(kb_type: str, query: str, result: dict) -> None:
    """Store result in cache; prune stale entries if cache exceeds 500 items."""
    key = _cache_key(kb_type, query)
    _QUERY_CACHE[key] = (result, time.time())
    if len(_QUERY_CACHE) > 500:
        cutoff = time.time() - CACHE_TTL_SECONDS
        for k in list(_QUERY_CACHE.keys()):
            if _QUERY_CACHE[k][1] < cutoff:
                del _QUERY_CACHE[k]


def invalidate_cache(kb_type: str | None = None) -> int:
    """Invalidate all cache entries (or just for a specific kb_type). Returns count removed."""
    removed = 0
    if kb_type is None:
        removed = len(_QUERY_CACHE)
        _QUERY_CACHE.clear()
    else:
        # We can't easily filter by kb_type without re-hashing, so clear all
        removed = len(_QUERY_CACHE)
        _QUERY_CACHE.clear()
    return removed


# ─── Model name constants ─────────────────────────────────────────────────────

# Gemini model names (used when Gemma/OpenRouter is unavailable)
_GEMINI_MODELS: dict[str, str] = {
    "regulations": "gemini-3.1-flash-lite-preview",
    "products":    "gemini-3.1-flash-lite-preview",
}

# Display names shown in the chat UI header (reflects primary provider = Gemma 4)
MODELS: dict[str, str] = {
    "regulations": "google/gemma-4-31b-it",
    "products":    "google/gemma-4-31b-it",
}

CLAUDE_MODEL = "claude-sonnet-4-6"

# ─── Stopwords to filter from search queries ─────────────────────────────────

STOPWORDS = frozenset({
    "the", "a", "an", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "only", "own", "same", "than", "too",
    "very", "just", "because", "but", "and", "or", "nor", "so",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "it", "its", "if", "up", "any", "also", "tell", "me",
    # Note: "not", "is", "for", "about", "why" intentionally excluded —
    # these carry semantic meaning in regulatory queries
    # e.g. "is this banned", "not for medicinal use", "for what purpose"
})


# ─── Query expansion ──────────────────────────────────────────────────────────

def _expand_query(query: str, kb_type: str, gemini_api_key: str = "") -> str:
    """
    Expand a short query (< 6 words) into a richer form for better retrieval.
    Uses Gemini Flash (cheap/fast). Falls back to original query on any failure.
    Only expands queries with fewer than 6 meaningful (non-stopword) words.
    """
    meaningful_words = [w for w in query.split() if w.lower() not in STOPWORDS and len(w) >= 3]
    if len(meaningful_words) >= 6 or not gemini_api_key:
        return query

    domain = (
        "Indian food and supplement regulations (FSSAI, Legal Metrology, AYUSH, BIS)"
        if kb_type == "regulations"
        else "nutraceutical product compliance data and label analysis results"
    )

    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        prompt = (
            f"Expand this short search query into a detailed search query for {domain}. "
            f"Return ONLY the expanded query (one sentence, max 25 words). No preamble.\n"
            f"Original query: {query}"
        )
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 60},
        )
        expanded = response.text.strip().strip('"').strip("'")
        if expanded and len(expanded) > len(query):
            logger.info("[llm-expand] %r → %r", query[:60], expanded[:80])
            return expanded
    except Exception as exc:
        logger.debug("[llm-expand] failed: %s", exc)
    return query


# ─── System prompts ───────────────────────────────────────────────────────────

SYSTEM_PROMPTS: dict[str, str] = {
    "regulations": (
        "You are RegBite's Regulatory Compliance Expert for India — an authoritative AI assistant "
        "specializing in Indian food and supplement regulations.\n\n"
        "YOUR KNOWLEDGE BASE covers five regulatory frameworks:\n"
        "1. **FSSAI** — Food Safety and Standards Authority of India regulations for health supplements, "
        "nutraceuticals, food labelling, ingredient restrictions, and health claims (FSS Act 2006, "
        "FSS Health Supplements Regulations 2022, FSS Labelling & Display Regulations 2020 Version VIII Sept 2025, "
        "FSS Food Products Standards & Food Additives First Amendment 2025, FSSAI Licensing Amendment 2026).\n"
        "2. **Legal Metrology** — Packaged Commodities Rules 2011 (as amended 2017, 2022) covering MRP declarations, "
        "net quantity, manufacturer/importer details, bilingual declarations, unit sale price, and consumer care requirements.\n"
        "3. **AYUSH** — Ayurvedic, Siddha, and Unani (ASU) drug regulations under the Drugs and Cosmetics Act 1940, "
        "covering formulation labelling, Schedule E(1) restricted ingredients, Bhasma/Rasa metal content, "
        "AYUSH Premium Mark, and the Drugs and Magic Remedies Act 1954 prohibitions.\n"
        "4. **BIS** — Bureau of Indian Standards IS 4926:2023 and IS 7022:2023 for supplement quality standards.\n"
        "5. **DGFT** — Foreign Trade Policy 2023 import requirements for health supplements.\n\n"
        "RESPONSE GUIDELINES:\n"
        "- Answer using ONLY the provided context. If context is insufficient, say so explicitly.\n"
        "- Always cite the specific rule code (e.g. FSSAI-NUTRA-LBL-003) and regulation source.\n"
        "- Format citations as: **[RULE_CODE]** — regulation source — section/clause if known.\n"
        "- At the end of your response, add a 'Sources used:' section listing the document titles "
        "from which you drew each fact (use the [Source: ...] tags in the context).\n"
        "- When multiple rules apply, list them in order of severity (CRITICAL → HIGH → MEDIUM → LOW).\n"
        "- For remediation questions, provide specific, actionable steps the manufacturer should take.\n"
        "- Do NOT hallucinate rule codes, regulation numbers, or section references.\n"
        "- CRITICAL: If a rule code is not explicitly present in the provided context, "
        "do NOT invent one. Write 'Rule code not available in context' instead.\n"
        "- If the context does not contain enough information to answer confidently, "
        "say: 'I don't have sufficient information in my knowledge base to answer this accurately.'\n"
        "- Use bullet points and bold text for readability."
    ),
    "products": (
        "You are RegBite's Product Compliance Analyst — an AI assistant that helps "
        "administrators understand product compliance status on the RegBite platform.\n\n"
        "YOUR KNOWLEDGE BASE contains:\n"
        "- Product data (names, SKUs, categories, descriptions)\n"
        "- Label analysis results (extracted label fields, extraction confidence)\n"
        "- Compliance check outcomes (PASS/FAIL/WARNING per rule, scores, remediation)\n\n"
        "RESPONSE GUIDELINES:\n"
        "- Always reference products by name and SKU when available.\n"
        "- Quote compliance scores and specific failing rule codes.\n"
        "- For failing checks, include the remediation steps from the knowledge base.\n"
        "- Compare products when asked (e.g. 'which product has the most violations?').\n"
        "- Keep responses factual — do not invent compliance data.\n"
        "- CRITICAL: Only report compliance scores, rule codes, and check results that appear "
        "explicitly in the provided context. Do NOT estimate or fabricate values.\n"
        "- If asked about a product not in the context, say: "
        "'This product is not in my current knowledge base — please reseed the Products KB.'\n"
        "- Use tables or bullet points for multi-product comparisons."
    ),
}


# ─── Text chunking ────────────────────────────────────────────────────────────

def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
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
    Skips exact-duplicate chunks already present in this KB.
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
    inserted = 0
    for i, chunk_content in enumerate(chunks):
        # Skip exact-duplicate chunks already in this KB
        existing = db.query(KBChunk.id).filter(
            KBChunk.kb_type == KBType(kb_type),
            KBChunk.content == chunk_content,
        ).first()
        if existing:
            continue
        db.add(KBChunk(
            document_id=doc.id,
            kb_type=KBType(kb_type),
            chunk_index=i,
            content=chunk_content,
        ))
        inserted += 1

    doc.chunk_count = inserted
    db.commit()
    return doc


# ─── Bulk FSSAI PDF ingestion ────────────────────────────────────────────────

def ingest_fssai_pdfs(db, folder_path: str = None) -> dict:
    """
    Bulk-ingest all FSSAI regulation/gazette notification PDFs from the FSSAI/
    folder into the Regulations knowledge base.

    Additive — skips PDFs whose source key already exists in the KB.
    Uses pdfplumber for text extraction, same as the single-file upload handler.

    Returns: {"status": ..., "total_files": N, "ingested": N, "skipped": N,
              "failed": N, "errors": [...]}
    """
    import os
    from pathlib import Path
    from app.models import KBDocument, KBType

    if folder_path is None:
        # FSSAI/ sits alongside the app/ package inside nutracomply/
        # Dockerfile: COPY nutracomply/ /app  → runtime path is /app/app/services/llm_service.py
        # 3 x .parent: services → app → nutracomply (= /app on Railway)
        nutracomply_root = Path(__file__).resolve().parent.parent.parent
        folder_path = str(nutracomply_root / "FSSAI")

    if not os.path.isdir(folder_path):
        return {"status": "error", "message": f"Folder not found: {folder_path}",
                "total_files": 0, "ingested": 0, "skipped": 0, "failed": 0, "errors": []}

    # Gather all PDFs
    pdf_files = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(".pdf")
    ])

    if not pdf_files:
        return {"status": "no_pdfs", "message": "No PDF files found in folder",
                "total_files": 0, "ingested": 0, "skipped": 0, "failed": 0, "errors": []}

    # Get existing sources to skip already-ingested files
    existing_sources = {
        d.source for d in
        db.query(KBDocument.source).filter(
            KBDocument.kb_type == KBType.REGULATIONS,
            KBDocument.is_active == True,
        ).all()
    }

    ingested = 0
    skipped = 0
    failed = 0
    errors = []

    for filename in pdf_files:
        source_key = f"fssai:{filename}"

        # Skip if already ingested
        if source_key in existing_sources:
            skipped += 1
            continue

        filepath = os.path.join(folder_path, filename)
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                content = "\n\n".join(
                    (page.extract_text() or "") for page in pdf.pages
                )

            content = content.strip()
            if not content or len(content) < 50:
                errors.append(f"{filename}: empty or unreadable")
                failed += 1
                continue

            # Derive a human-readable title from the filename
            title = _fssai_filename_to_title(filename)

            _ingest_document(
                db, "regulations",
                title=title,
                source=source_key,
                content=content,
            )
            ingested += 1

            # Log progress every 25 files
            if (ingested + skipped + failed) % 25 == 0:
                logger.info("[fssai-ingest] Progress: %d ingested, %d skipped, %d failed of %d",
                            ingested, skipped, failed, len(pdf_files))

        except Exception as exc:
            errors.append(f"{filename}: {str(exc)[:120]}")
            failed += 1

    total = len(pdf_files)
    status = "done" if ingested > 0 else ("up_to_date" if skipped == total else "error")
    logger.info("[fssai-ingest] Complete: %d ingested, %d skipped, %d failed of %d total",
                ingested, skipped, failed, total)

    return {
        "status": status,
        "total_files": total,
        "ingested": ingested,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:20],  # cap error list
    }


def _fssai_filename_to_title(filename: str) -> str:
    """Convert an FSSAI PDF filename to a readable document title.

    Example: '5b56d3936c5e8Gazette_Notification_Gluten_11_05_2016 (1).pdf'
           → 'FSSAI Gazette Notification: Gluten (11/05/2016)'
    """
    import re
    name = filename.rsplit(".", 1)[0]  # strip .pdf
    name = re.sub(r"^\w{12,14}", "", name)  # strip leading hex ID
    name = re.sub(r"\s*\(\d+\)\s*$", "", name)  # strip " (1)" suffixes
    name = name.replace("_", " ").strip()

    # Extract date if present at end (DD_MM_YYYY pattern)
    date_match = re.search(r"(\d{2})\s+(\d{2})\s+(\d{4})$", name)
    date_str = ""
    if date_match:
        date_str = f" ({date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)})"
        name = name[:date_match.start()].strip()

    # Clean up "Gazette Notification" prefix
    name = re.sub(r"^Gazette\s+Notification\s*", "", name, flags=re.IGNORECASE)

    if name:
        return f"FSSAI Gazette Notification: {name}{date_str}"
    return f"FSSAI Document: {filename[:80]}"


# ─── KB seeding from DB ───────────────────────────────────────────────────────

def seed_regulations_kb(db, framework: str | None = None) -> dict:
    """
    Auto-populate the Regulations knowledge base from existing DB rows.
    Additive — only inserts documents whose source doesn't already exist.
    Data is permanently stored and never auto-deleted.
    Sources: ComplianceRule, RegulationChange, Ingredient.

    Args:
        framework: None = seed all rules; "fssai" = FSSAI-* rules + changes + ingredients;
                   "ayush" = AYUSH-* rules only; "legal_metrology" = LM-* rules only.
    """
    from app.models import KBDocument, KBType, ComplianceRule, RegulationChange, Ingredient

    # Rule-code prefix map
    _prefix = {
        "fssai":           "FSSAI",
        "ayush":           "AYUSH",
        "legal_metrology": "LM",
    }

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
    rules_q = db.query(ComplianceRule).filter(ComplianceRule.active == True)
    if framework and framework in _prefix:
        rules_q = rules_q.filter(ComplianceRule.rule_code.like(f"{_prefix[framework]}%"))
    for rule in rules_q.all():
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

    # ── Regulation Changes + Ingredients — FSSAI scope only ──────────────────
    if framework in (None, "fssai"):
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
    if count > 0:
        invalidate_cache("regulations")
    return {"status": "seeded" if count > 0 else "up_to_date", "document_count": total, "new_documents": count}


def seed_products_kb(db, force_update_product_id: int | None = None) -> dict:
    """
    Auto-populate the Products knowledge base from existing DB rows.
    Additive — only inserts products whose source doesn't already exist.
    Data is permanently stored and never auto-deleted.
    Sources: Product + latest LabelVersion + ComplianceCheck failures.

    Args:
        db: SQLAlchemy session
        force_update_product_id: If given, delete and re-ingest the KB document
            for this specific product (allows fresh compliance data after a scan).
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

        if force_update_product_id and product.id == force_update_product_id:
            # Delete existing KB document for this product to force re-ingest
            old_doc = db.query(KBDocument).filter(
                KBDocument.source == source,
                KBDocument.kb_type == KBType.PRODUCTS,
            ).first()
            if old_doc:
                db.delete(old_doc)
                db.flush()
                existing_sources.discard(source)

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

            from app.services.compliance_engine import calculate_compliance_score as _calc_score
            score = _calc_score(checks)
            checks_summary = (
                f"\nLabel Analysis (uploaded {latest_lv.uploaded_at.strftime('%Y-%m-%d')}):\n"
                f"Compliance Score: {score}% ({passed}/{total} checks passed, severity-weighted)\n"
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
    if count > 0:
        invalidate_cache("products")
    return {"status": "seeded" if count > 0 else "up_to_date", "document_count": total, "new_documents": count}


# ─── Context retrieval ────────────────────────────────────────────────────────

def retrieve_context(kb_type: str, query: str, db, top_k: int = 10) -> list[dict]:
    """
    Search kb_chunks for the most relevant chunks matching *query* using
    LIKE-based multi-word scoring with title boosting and stopword filtering.
    No pgvector required.

    v2 improvements:
      - Stopword filtering for better signal-to-noise
      - Title matching gives 2x boost (document titles are high-signal)
      - Minimum relevance threshold filters low-quality matches
      - Returns relevance scores for LLM context transparency

    v5 improvements:
      - Phrase-level matching: +3 points per consecutive word-pair (bigram) found in content

    Returns a list of dicts: {"chunk_id", "content", "document_title", "relevance_score"}.
    """
    from app.models import KBChunk, KBDocument, KBType
    from sqlalchemy import or_, case

    # Tokenize: remove stopwords, keep words ≥ 3 chars, cap at 10 terms
    words = [
        w.strip().lower()
        for w in query.split()
        if len(w.strip()) >= 3 and w.strip().lower() not in STOPWORDS
    ][:10]

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
             "document_title": c.document.title if c.document else "Unknown",
             "relevance_score": 0}
            for c in rows
        ]

    # Build content score: sum of per-word CASE expressions (1 point each)
    content_score = case((KBChunk.content.ilike(f"%{words[0]}%"), 1), else_=0)
    for word in words[1:]:
        content_score = content_score + case((KBChunk.content.ilike(f"%{word}%"), 1), else_=0)

    # Build title score: 2x boost for matches in document title (titles are high-signal)
    title_score = case((KBDocument.title.ilike(f"%{words[0]}%"), 2), else_=0)
    for word in words[1:]:
        title_score = title_score + case((KBDocument.title.ilike(f"%{word}%"), 2), else_=0)

    # Phrase score: +3 for each consecutive word pair found as a phrase
    phrase_score = None
    if len(words) >= 2:
        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i+1]}"
            ps = case((KBChunk.content.ilike(f"%{phrase}%"), 3), else_=0)
            phrase_score = ps if phrase_score is None else phrase_score + ps

    total_score = content_score + title_score
    if phrase_score is not None:
        total_score = total_score + phrase_score

    or_conditions = or_(
        *[KBChunk.content.ilike(f"%{w}%") for w in words],
        *[KBDocument.title.ilike(f"%{w}%") for w in words],
    )

    results = (
        db.query(KBChunk, total_score.label("score"))
        .join(KBDocument, KBChunk.document_id == KBDocument.id)
        .filter(
            KBChunk.kb_type == KBType(kb_type),
            KBDocument.is_active == True,
            or_conditions,
        )
        .order_by(total_score.desc(), KBChunk.id)
        .limit(top_k * 2)  # fetch extra, then filter by minimum relevance
        .all()
    )

    # Minimum relevance threshold: at least 20% of search terms should match
    min_score = max(1, len(words) // 5)
    filtered = [
        {
            "chunk_id": row.KBChunk.id,
            "content":  row.KBChunk.content,
            "document_title": (
                row.KBChunk.document.title if row.KBChunk.document else "Unknown"
            ),
            "relevance_score": row.score,
        }
        for row in results
        if row.score >= min_score
    ][:top_k]

    # If filtering was too aggressive, return top results anyway
    if not filtered and results:
        filtered = [
            {
                "chunk_id": row.KBChunk.id,
                "content":  row.KBChunk.content,
                "document_title": (
                    row.KBChunk.document.title if row.KBChunk.document else "Unknown"
                ),
                "relevance_score": row.score,
            }
            for row in results
        ][:top_k]

    return filtered


# ─── Context formatting helper ────────────────────────────────────────────────

def _build_context(kb_type: str, query: str, db):
    """
    Retrieve chunks and format them into context text + quality indicator.
    Applies query expansion for short queries, then merges expanded + original results.
    Returns (context_chunks, system_prompt, user_message).
    """
    from app.config import get_settings as _get_settings
    _settings = _get_settings()
    expanded_query = _expand_query(query, kb_type, _settings.gemini_api_key or "")

    # For the products KB, use a much higher top_k so broad "list all" queries
    # return every product document rather than just the top 15 chunks.
    top_k_primary = 80 if kb_type == "products" else 15

    context_chunks = retrieve_context(kb_type, expanded_query, db, top_k=top_k_primary)
    # If expansion found different results and original query returns more, merge
    if expanded_query != query:
        original_chunks = retrieve_context(kb_type, query, db, top_k=max(8, top_k_primary // 2))
        seen_ids = {c["chunk_id"] for c in context_chunks}
        for c in original_chunks:
            if c["chunk_id"] not in seen_ids:
                context_chunks.append(c)
                seen_ids.add(c["chunk_id"])
        context_chunks = context_chunks[:top_k_primary]  # cap at adjusted limit

    if context_chunks:
        max_score = max(c["relevance_score"] for c in context_chunks) or 1
        context_parts = []
        for c in context_chunks:
            relevance = "HIGH" if c["relevance_score"] >= max_score * 0.7 else (
                "MEDIUM" if c["relevance_score"] >= max_score * 0.4 else "LOW"
            )
            context_parts.append(
                f"[Source: {c['document_title']} | Relevance: {relevance}]\n{c['content']}"
            )
        context_text = "\n\n---\n\n".join(context_parts)

        high_relevance_count = sum(
            1 for c in context_chunks if c["relevance_score"] >= max_score * 0.7
        )
        if high_relevance_count >= 3:
            context_quality = "Strong context available — answer with confidence."
        elif high_relevance_count >= 1:
            context_quality = "Partial context available — answer what you can, note gaps."
        else:
            context_quality = "Weak context match — be cautious, acknowledge limitations."
    else:
        context_text = "[No relevant context found in knowledge base]"
        context_quality = "No context found — tell the user you don't have this information."

    system_prompt = SYSTEM_PROMPTS.get(kb_type, SYSTEM_PROMPTS["regulations"])

    user_message = (
        f"KNOWLEDGE BASE CONTEXT ({context_quality}):\n"
        f"{context_text}\n\n"
        f"USER QUESTION: {query}"
    )

    return context_chunks, system_prompt, user_message


# ─── Gemini call ──────────────────────────────────────────────────────────────

def _call_gemini(model_name: str, system_prompt: str, user_message: str,
                 history: list, api_key: str) -> str:
    """Call Gemini and return the reply text. Raises on failure."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
    )

    # Build Gemini history from last 20 turns (roles: "user" / "model")
    gemini_history = [
        {"role": msg["role"], "parts": [msg["content"]]}
        for msg in history[-20:]
    ]

    chat = model.start_chat(history=gemini_history)
    response = chat.send_message(
        user_message,
        generation_config={"temperature": 0.2, "max_output_tokens": 2048},
    )
    return response.text.strip()


# ─── Gemma 4 via OpenRouter ──────────────────────────────────────────────────

def _call_gemma_chat(system_prompt: str, user_message: str,
                     history: list, api_key: str,
                     model_name: str) -> str:
    """Call Gemma 4 via OpenRouter's OpenAI-compatible API. Raises on failure."""
    import httpx
    from app.config import get_settings as _gs
    api_url = _gs().openrouter_api_url

    url = api_url.rstrip("/") + "/chat/completions"
    headers = {
        "content-type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://steadfast-courage-production-0f66.up.railway.app",
        "X-Title": "RegBite",
    }

    # Build OpenAI-style messages: system + history + current user message
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-20:]:
        role = "assistant" if msg["role"] == "model" else "user"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.2,
    }

    resp = httpx.post(url, headers=headers, json=payload, timeout=120.0)

    if not resp.is_success:
        # Extract the full OpenRouter error message before discarding the response
        try:
            err_body = resp.json()
            # OpenRouter wraps errors as {"error": {"message": "...", "code": ...}}
            err_detail = (
                err_body.get("error", {}).get("message")
                or err_body.get("message")
                or str(err_body)[:400]
            )
        except Exception:
            err_detail = resp.text[:400]
        raise ValueError(
            f"OpenRouter HTTP {resp.status_code} — {err_detail}"
        )

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


# ─── Claude (Anthropic) fallback ─────────────────────────────────────────────

def _call_claude(system_prompt: str, user_message: str,
                 history: list, api_key: str) -> str:
    """Call Claude as fallback and return the reply text. Raises on failure."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Convert history to Claude message format (role: "user" / "assistant")
    # Use last 20 turns for broader context
    claude_messages = []
    for msg in history[-20:]:
        role = "assistant" if msg["role"] == "model" else "user"
        claude_messages.append({"role": role, "content": msg["content"]})

    # Add the current user message with context
    claude_messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=claude_messages,
        temperature=0.2,
    )
    return response.content[0].text.strip()


# ─── Main ask_llm entry point ────────────────────────────────────────────────

def ask_llm(kb_type: str, query: str, history: list, db) -> dict:
    """
    RAG pipeline: retrieve context -> build prompt -> call LLM.

    Priority: Gemini → Gemma 4 (self-hosted fallback) → Claude (paid fallback).

    Args:
        kb_type:  "regulations" or "products"
        query:    current user message
        history:  list of {"role":"user"|"model", "content":"..."} dicts
        db:       SQLAlchemy session

    Returns:
        {"reply": str, "context_used": [document_title, ...], "provider": "gemma"|"gemini"|"claude"}
        On error: {"reply": error_msg, "context_used": [], "error": error_code}
    """
    from app.config import get_settings
    settings = get_settings()

    has_gemma  = bool(settings.gemma_enabled and settings.openrouter_api_key)
    has_gemini = bool(settings.gemini_api_key)
    has_claude = bool(settings.anthropic_api_key)

    if not has_gemma and not has_gemini and not has_claude:
        return {
            "reply": (
                "No LLM provider is configured. "
                "Set OPENROUTER_API_KEY, GEMINI_API_KEY, or ANTHROPIC_API_KEY in your environment."
            ),
            "context_used": [],
            "error": "no_api_key",
        }

    # Check cache first (skip for very short queries that are likely unique)
    if len(query.split()) >= 3:
        cached = _get_cached(kb_type, query)
        if cached:
            logger.info("[llm-cache] HIT for %r", query[:60])
            return {**cached, "cached": True}

    # Build RAG context
    context_chunks, system_prompt, user_message = _build_context(kb_type, query, db)
    context_titles = [c["document_title"] for c in context_chunks]
    gemini_model = _GEMINI_MODELS.get(kb_type, "gemini-3.1-flash-lite-preview")

    # ─── Provider priority (same for ALL kb_types): ───────────────────────────
    #   1. Gemma 4 via OpenRouter  — primary (self-hosted economics)
    #   2. Claude (Anthropic)      — paid fallback
    #   3. Gemini                  — last resort
    # ─────────────────────────────────────────────────────────────────────────

    gemma_error  = None
    claude_error = None
    gemini_error = None

    # ── Step 1: Gemma 4 via OpenRouter ───────────────────────────────────────
    if has_gemma:
        try:
            reply = _call_gemma_chat(system_prompt, user_message, history,
                                     settings.openrouter_api_key,
                                     settings.gemma_model_name)
            result = {
                "reply":        reply,
                "context_used": context_titles,
                "provider":     "gemma",
                "model":        settings.gemma_model_name,
            }
            _set_cache(kb_type, query, result)
            return result
        except Exception as exc:
            gemma_error = str(exc)
            logger.warning("[llm] Gemma failed for %s chat: %s", kb_type, gemma_error[:200])

    # ── Step 2: Claude fallback ───────────────────────────────────────────────
    if has_claude:
        try:
            reply = _call_claude(system_prompt, user_message,
                                 history, settings.anthropic_api_key)
            # Show why Gemma failed so the admin can diagnose it
            if gemma_error:
                # Trim to a readable length; strip noisy HTTP stack lines
                err_short = gemma_error.replace("\n", " ")[:160]
                fallback_note = f"\n\n---\n*⚠️ Gemma unavailable — Claude answered. Gemma error: `{err_short}`*"
            else:
                fallback_note = ""
            result = {
                "reply":        reply + fallback_note,
                "context_used": context_titles,
                "provider":     "claude",
                "model":        CLAUDE_MODEL,
            }
            _set_cache(kb_type, query, result)
            return result
        except Exception as exc:
            claude_error = str(exc)
            logger.error("[llm] Claude failed for %s chat: %s", kb_type, claude_error[:200])

    # ── Step 3: Gemini last resort ────────────────────────────────────────────
    if has_gemini:
        try:
            reply = _call_gemini(gemini_model, system_prompt, user_message,
                                 history, settings.gemini_api_key)
            notes = []
            if gemma_error:
                notes.append(f"Gemma: {gemma_error[:120]}")
            if claude_error:
                notes.append(f"Claude: {claude_error[:120]}")
            fallback_note = (
                f"\n\n---\n*⚠️ Gemini answered as last resort. " + " | ".join(notes) + "*"
                if notes else ""
            )
            result = {
                "reply":        reply + fallback_note,
                "context_used": context_titles,
                "provider":     "gemini",
                "model":        gemini_model,
            }
            _set_cache(kb_type, query, result)
            return result
        except Exception as exc:
            gemini_error = str(exc)
            logger.error("[llm] Gemini failed for %s chat: %s", kb_type, gemini_error[:200])

    # All providers failed
    errors = []
    if gemma_error:
        errors.append(f"Gemma ({settings.gemma_model_name}): {gemma_error[:150]}")
    if claude_error:
        errors.append(f"Claude ({CLAUDE_MODEL}): {claude_error[:150]}")
    if gemini_error:
        errors.append(f"Gemini ({gemini_model}): {gemini_error[:150]}")
    return {
        "reply": "All LLM providers failed.\n\n" + "\n\n".join(errors) if errors else "No LLM provider available.",
        "context_used": [],
        "error": "all_providers_failed",
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
