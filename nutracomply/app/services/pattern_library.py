"""
Pattern Library — learns extraction patterns from successful Claude extractions.

After each successful Claude extraction (confidence >= 0.80), field values and
surrounding OCR context are stored in the ExtractionPattern table. Future local
extractions query this library via TF-IDF cosine similarity to fill fields that
regex alone cannot extract.

This creates a self-improving loop: more Claude extractions → fewer future calls.
"""

from typing import Optional
from sqlalchemy.orm import Session


# Fields that benefit from learned patterns (excludes booleans and complex tables
# that are better handled by regex or Claude respectively)
LEARNABLE_FIELDS = [
    "product_name",
    "product_type_declaration",
    "manufacturer_details",
    "country_of_origin",
    "target_consumer",
    "storage_conditions",
    "customer_care_details",
    "formulation_reference",
]

# Chars of surrounding OCR text to store as matching context
CONTEXT_WINDOW = 400

# Minimum cosine similarity to trust a pattern match
MIN_SIMILARITY = 0.80

# Minimum number of stored patterns before we attempt lookup (cold start guard)
MIN_PATTERNS_FOR_LOOKUP = 5


def _extract_context(field_value: str, ocr_text: str) -> str:
    """Return the OCR text window surrounding where field_value appears."""
    if not field_value or not ocr_text:
        return ocr_text[:CONTEXT_WINDOW] if ocr_text else ""

    # Find approximate location of the value in OCR text
    search_str = str(field_value).lower()[:30]
    idx = ocr_text.lower().find(search_str)
    if idx == -1:
        return ocr_text[:CONTEXT_WINDOW]

    half = CONTEXT_WINDOW // 2
    start = max(0, idx - half)
    end = min(len(ocr_text), idx + len(str(field_value)) + half)
    return ocr_text[start:end]


def learn_from_extraction(
    extraction: dict,
    ocr_text: str,
    label_version_id: int,
    db: Session,
    confidence: float = 0.0,
) -> None:
    """
    Persist field-level patterns from a successful Claude extraction.

    Called after extractions with confidence >= 0.80. Only stores learnable
    string fields that have non-empty values.
    """
    from app.models import ExtractionPattern

    stored = 0
    for field in LEARNABLE_FIELDS:
        val = extraction.get(field)
        if not val or not isinstance(val, str) or len(val.strip()) < 2:
            continue

        context = _extract_context(val, ocr_text)
        pattern = ExtractionPattern(
            field_name=field,
            field_value=val.strip(),
            ocr_context=context,
            source_label_id=label_version_id,
            confidence=confidence,
        )
        db.add(pattern)
        stored += 1

    if stored:
        try:
            db.commit()
            print(
                f"[pattern-library] Stored {stored} patterns from label {label_version_id}",
                flush=True,
            )
        except Exception as e:
            db.rollback()
            print(f"[pattern-library] Failed to store patterns: {e}", flush=True)


def lookup_missing_fields(
    extraction: dict,
    ocr_text: str,
    db: Session,
) -> dict:
    """
    For each learnable field that is missing in extraction, find the most similar
    past OCR context and fill in the stored value.

    Optimised: one DB query for all missing fields combined (was N queries),
    then one TF-IDF pass per field on in-memory data.
    """
    from app.models import ExtractionPattern

    missing = [f for f in LEARNABLE_FIELDS if not extraction.get(f)]
    if not missing:
        return extraction

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
    except ImportError:
        return extraction  # scikit-learn not yet installed

    # Single query for ALL missing fields — avoids N round-trips
    all_patterns = (
        db.query(ExtractionPattern)
        .filter(ExtractionPattern.field_name.in_(missing))
        .order_by(ExtractionPattern.id.desc())
        .limit(200 * len(missing))   # generous cap across all fields
        .all()
    )
    if len(all_patterns) < MIN_PATTERNS_FOR_LOOKUP:
        return extraction  # cold-start guard

    # Group by field in Python (free — already fetched)
    by_field: dict = {}
    for p in all_patterns:
        by_field.setdefault(p.field_name, []).append(p)
    # Keep at most 200 per field (already ordered DESC so first 200 = most recent)
    for f in by_field:
        by_field[f] = by_field[f][:200]

    query_context = ocr_text[: CONTEXT_WINDOW * 2]

    for field in missing:
        patterns = by_field.get(field)
        if not patterns:
            continue

        contexts = [p.ocr_context for p in patterns]
        try:
            vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
            matrix = vectorizer.fit_transform(contexts + [query_context])
            sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])

            if best_sim >= MIN_SIMILARITY:
                matched = patterns[best_idx].field_value
                extraction[field] = matched
                print(
                    f"[pattern-library] matched {field}={matched[:50]!r} "
                    f"(sim={best_sim:.2f})",
                    flush=True,
                )
        except Exception:
            continue

    return extraction
