"""
Local Extraction Service — extracts label fields without any API calls.

Three-tier approach:
  Tier 1: Regex + rule-based patterns (~22 fields, works day-1)
  Tier 2: Pattern library learned from past Claude extractions (improves over time)
  Tier 3: Structural parsers (nutrition table, ingredient block)

Confidence score (0.0–1.0) is a weighted fill rate. If confidence reaches
the configured threshold (default 0.72), the caller can skip Claude entirely.
"""

import re
from typing import Optional


# ─── Field weights for confidence scoring ────────────────────────────────────
# CRITICAL (3): essential for FSSAI compliance — missing = definitely non-compliant
# HIGH (2): important but not always present on all product types
# MEDIUM (1): nice-to-have fields

FIELD_WEIGHTS = {
    "fssai_license_number": 3,
    "product_name": 3,
    "net_quantity": 3,
    "expiry_date": 3,
    "manufacturer_details": 2,
    "ingredient_list": 2,
    "nutritional_table": 2,
    "serving_size": 1,
    "manufacturing_date": 1,
    "batch_number": 1,
    "storage_conditions": 1,
    "veg_nonveg_mark": 1,
    "mrp": 1,
    "country_of_origin": 1,
    "target_consumer": 1,
    "customer_care_details": 1,
    "product_type_declaration": 1,
    "allergen_declarations": 1,
    "not_for_medicinal_use": 1,
    "consult_doctor_advisory": 1,
    "keep_out_of_reach_children": 1,
    "not_exceed_daily_usage_advisory": 1,
    "rda_percentages": 1,
    "health_claims": 1,
    "warnings": 1,
}

TOTAL_WEIGHT = sum(FIELD_WEIGHTS.values())


def _is_filled(val) -> bool:
    """Return True if a field value is considered populated."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (list, dict)):
        return len(val) > 0
    if isinstance(val, str):
        return bool(val.strip())
    return bool(val)


def _calculate_local_confidence(extraction: dict) -> float:
    """Weighted confidence: earned_weight / total_weight."""
    earned = 0
    for field, weight in FIELD_WEIGHTS.items():
        if _is_filled(extraction.get(field)):
            earned += weight
    return round(earned / TOTAL_WEIGHT, 3)


# ─── Tier 1: Regex extraction ─────────────────────────────────────────────────

def _extract_product_name(text: str) -> Optional[str]:
    """Heuristic: look for explicit 'Product Name:' label or dosage-form lines."""
    # Explicit label
    m = re.search(r'product\s*name[:\s]+([^\n]{3,80})', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Lines ending with common dosage forms
    m = re.search(
        r'^([A-Z][A-Za-z0-9\s\+®™\-]{3,55}'
        r'(?:Capsules?|Tablets?|Powder|Drops?|Syrup|Softgels?|Gummies?|Chews?))\s*$',
        text, re.MULTILINE
    )
    if m:
        return m.group(1).strip()

    # Short all-caps line near the top (brand/product name pattern)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:12]:
        if (4 <= len(line) <= 60
                and line.isupper()
                and not re.search(r'\d{6,}', line)
                and not re.search(r'\b(?:MFG|MRP|FSSAI|BATCH|LOT|GST|PAN)\b', line)):
            return line

    return None


def _extract_tier1(text: str) -> dict:
    """
    Tier 1: regex extraction covering ~22 label fields.
    Builds on and extends the existing _rule_based_extraction + _cross_check_with_ocr logic.
    """
    text_lower = text.lower()

    def has(phrase: str) -> bool:
        return phrase.lower() in text_lower

    # ── FSSAI license (14-digit number) ─────────────────────────────────────
    fssai_match = re.search(r'\b(\d{14})\b', text)
    fssai_num = fssai_match.group(1) if fssai_match else None

    # ── Net quantity ─────────────────────────────────────────────────────────
    qty_match = re.search(
        r'(?:net\s+(?:wt\.?|weight|qty\.?|quantity|contents?)[:\s]*)'
        r'([\d.,]+\s*(?:g|mg|kg|ml|l|tablets?|capsules?|softgels?|sachets?|pieces?))',
        text, re.IGNORECASE
    )
    net_qty = qty_match.group(0).strip() if qty_match else None

    # ── Batch / Lot number ───────────────────────────────────────────────────
    batch_match = re.search(
        r'(?:batch|lot)\s*(?:no\.?|number|#)?[:\s]+([A-Z0-9][A-Z0-9\-/]{1,20})',
        text, re.IGNORECASE
    )
    batch = batch_match.group(1).strip() if batch_match else None

    # ── Expiry / best before ─────────────────────────────────────────────────
    expiry_match = re.search(
        r'(?:best\s*before|expiry\s*(?:date)?|use\s*by|exp\.?|bb)[:\s]+([^\n,]{4,25})',
        text, re.IGNORECASE
    )
    expiry = expiry_match.group(1).strip() if expiry_match else None

    # ── Manufacturing date ───────────────────────────────────────────────────
    mfg_match = re.search(
        r'(?:mfg\.?\s*(?:date|dt\.?)|date\s*of\s*mfg\.?|manufactured\s*on)[:\s]+([^\n,]{4,25})',
        text, re.IGNORECASE
    )
    mfg_date = mfg_match.group(1).strip() if mfg_match else None

    # ── Product type declaration ─────────────────────────────────────────────
    product_type = None
    for pt in [
        "HEALTH SUPPLEMENT", "NUTRACEUTICAL", "FUNCTIONAL FOOD",
        "NOVEL FOOD", "AYURVEDIC PROPRIETARY MEDICINE", "AYURVEDIC",
        "FOOD SUPPLEMENT", "DIETARY SUPPLEMENT",
    ]:
        if pt.lower() in text_lower:
            product_type = pt
            break

    # ── Veg / Non-veg ────────────────────────────────────────────────────────
    veg_mark = None
    if re.search(r'\bnon[\s-]?veg(?:etarian)?\b', text_lower):
        veg_mark = "NON-VEG"
    elif re.search(r'\bveg(?:etarian)?\b', text_lower):
        veg_mark = "VEG"

    # ── MRP ──────────────────────────────────────────────────────────────────
    mrp_match = re.search(
        r'(?:MRP|M\.R\.P\.?)[:\s]*[₹Rs\.]*\s*([0-9,]+(?:\.\d{1,2})?)',
        text, re.IGNORECASE
    )
    mrp = mrp_match.group(0).strip() if mrp_match else None

    # ── Serving size ─────────────────────────────────────────────────────────
    srv_match = re.search(r'serving\s*size[:\s]*([^\n]{5,60})', text, re.IGNORECASE)
    serving_size = srv_match.group(1).strip() if srv_match else None

    # ── Storage conditions ────────────────────────────────────────────────────
    storage = None
    if any(has(w) for w in ("cool", "dry place", "sunlight", "below 30", "refrigerat", "room temperature")):
        store_match = re.search(r'store[^\n.]{5,120}', text, re.IGNORECASE)
        if store_match:
            storage = store_match.group(0).strip()

    # ── Manufacturer / Marketer details ──────────────────────────────────────
    mfr = None
    mfr_match = re.search(
        r'(?:manufactured\s+by|marketed\s+by|distributed\s+by|mfg\.\s*by)[:\s]*([^\n]{10,250})',
        text, re.IGNORECASE
    )
    if mfr_match:
        mfr = mfr_match.group(0).strip()

    # ── Country of origin ────────────────────────────────────────────────────
    coo = None
    coo_match = re.search(
        r'(?:country\s+of\s+origin|made\s+in)[:\s]+([A-Za-z\s]{3,30})',
        text, re.IGNORECASE
    )
    if coo_match:
        coo = coo_match.group(1).strip()
    elif has("made in india") or has("product of india"):
        coo = "India"

    # ── Target consumer ───────────────────────────────────────────────────────
    target = None
    target_match = re.search(
        r'(?:for\s+adults?|for\s+men\b|for\s+women\b|for\s+children|for\s+kids)[^\n.]{0,40}',
        text, re.IGNORECASE
    )
    if target_match:
        target = target_match.group(0).strip()

    # ── Customer care (email / toll-free / phone) ─────────────────────────────
    ccare = None
    email_match = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        ccare = email_match.group(0)
    else:
        # Toll-free 1800 or +91 mobile
        phone_match = re.search(
            r'(?:1800[\s\-]?\d{3}[\s\-]?\d{4}|\+91[\s\-]?\d{10}|\b\d{10}\b)', text
        )
        if phone_match:
            ccare = phone_match.group(0).strip()

    # ── Allergen declarations ────────────────────────────────────────────────
    allergens = []
    allerg_match = re.search(
        r'(?:contains?|may\s+contain)[:\s]*([^\n.]{5,150})', text, re.IGNORECASE
    )
    if allerg_match:
        snippet = allerg_match.group(1).lower()
        if any(a in snippet for a in (
            "gluten", "milk", "soy", "peanut", "tree nut", "wheat", "egg", "fish",
            "shellfish", "sesame", "mustard", "sulphite",
        )):
            allergens = [allerg_match.group(0).strip()]

    # ── Boolean advisory flags ────────────────────────────────────────────────
    not_med = has("not for medicinal use") or has("not a medicine") or has("not medicine")
    consult = has("consult") and any(has(w) for w in ("doctor", "physician", "dietitian", "healthcare"))
    keep_out = (has("out of reach") and has("children")) or has("keep away from children")
    not_exceed = has("not to exceed") or (has("do not exceed") and has("daily"))
    rda = (has("%rda") or has("% rda") or
           has("recommended daily allowance") or has("% daily value") or has("%dv"))

    # ── Warnings list ─────────────────────────────────────────────────────────
    warnings_list = []
    if not_med:
        warnings_list.append("Not for medicinal use")
    if keep_out:
        warnings_list.append("Keep out of reach of children")
    if consult:
        for line in text.splitlines():
            ll = line.lower()
            if "consult" in ll and any(w in ll for w in ("doctor", "physician", "dietitian")):
                warnings_list.append(line.strip())
                break

    # ── Product name (heuristic) ─────────────────────────────────────────────
    product_name = _extract_product_name(text)

    return {
        "product_name": product_name,
        "product_type_declaration": product_type,
        "fssai_license_number": fssai_num,
        "net_quantity": net_qty,
        "serving_size": serving_size,
        "manufacturing_date": mfg_date,
        "expiry_date": expiry,
        "batch_number": batch,
        "manufacturer_details": mfr,
        "country_of_origin": coo,
        "storage_conditions": storage,
        "target_consumer": target,
        "veg_nonveg_mark": veg_mark,
        "mrp": mrp,
        "customer_care_details": ccare,
        "formulation_reference": None,
        "ingredient_list": [],
        "nutritional_table": [],
        "rda_percentages": rda,
        "health_claims": [],
        "warnings": warnings_list,
        "allergen_declarations": allergens,
        "not_for_medicinal_use": not_med,
        "consult_doctor_advisory": consult,
        "keep_out_of_reach_children": keep_out,
        "not_exceed_daily_usage_advisory": not_exceed,
    }


# ─── Tier 3: Structural parsers ───────────────────────────────────────────────

def _parse_nutrition_table(text: str) -> list:
    """
    Extract nutrition facts table rows from OCR text.
    Returns list of {nutrient, per_serving, per_100g, rda_percent} dicts.
    """
    rows = []
    seen = set()

    nutrient_re = re.compile(
        r'(Energy|Protein|Carbohydrate[s]?|Total\s+Fat|Saturated\s+Fat|Trans\s+Fat|'
        r'Dietary\s+Fibre?|Fibre|Sugar[s]?|Sodium|Calcium|Iron|Vitamin\s+[A-Z][0-9A-Za-z]*|'
        r'Zinc|Magnesium|Phosphorus|Potassium|Folate|Folic\s+Acid|Chromium|Selenium|'
        r'Omega[\s-]?\d|DHA|EPA|Biotin|Niacin|Riboflavin|Thiamin[e]?|Pantothenic|'
        r'Ashwagandha|Turmeric|Curcumin|Collagen|Glucosamine|Chondroitin|'
        r'Lysine|Leucine|Isoleucine|Valine|Arginine|Creatine|Caffeine|Taurine|'
        r'CoQ10|Coenzyme\s+Q10|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+Extract)'
        r'[^\n]{0,100}',
        re.IGNORECASE
    )

    for m in nutrient_re.finditer(text):
        line = m.group(0)
        nutrient_name = m.group(1).strip()
        key = nutrient_name.lower()

        if key in seen:
            continue

        # Extract numeric values + units from the line
        value_re = re.findall(r'(\d+(?:\.\d+)?)\s*(mg|mcg|µg|g|kcal|kJ|IU|%|)', line)
        if not value_re:
            continue

        per_serving = None
        per_100g = None
        rda_pct = None

        for num, unit in value_re:
            val_str = f"{num}{(' ' + unit.strip()) if unit.strip() else ''}"
            if unit == "%":
                rda_pct = val_str
            elif per_serving is None:
                per_serving = val_str
            elif per_100g is None:
                per_100g = val_str

        if per_serving:
            seen.add(key)
            rows.append({
                "nutrient": nutrient_name,
                "per_serving": per_serving,
                "per_100g": per_100g,
                "rda_percent": rda_pct,
            })

    return rows


def _extract_ingredients(text: str) -> list:
    """
    Extract ingredient list from OCR text.
    Finds 'Ingredients:' section and splits on comma/semicolon.
    """
    m = re.search(
        r'(?:ingredients?|composition)[:\s]+([^\n]{20,}(?:\n[^\n]{5,}){0,15})',
        text, re.IGNORECASE
    )
    if not m:
        return []

    block = m.group(1)

    # Stop at section boundaries
    stop_match = re.search(
        r'(?:manufactured|marketed|storage|store\s|best\s+before|expiry|batch|'
        r'net\s+(?:wt|weight|qty)|mrp|warning|caution|direction)',
        block, re.IGNORECASE
    )
    if stop_match:
        block = block[:stop_match.start()]

    items = re.split(r'[,;]', block)
    result = []
    for item in items:
        item = re.sub(r'[\(\[].*?[\)\]]', '', item).strip()
        if 2 <= len(item) <= 100:
            result.append(item)

    return result[:50]


# ─── Main entry point ─────────────────────────────────────────────────────────

def extract_locally(ocr_text: str, db=None) -> tuple:
    """
    Extract label fields locally without any API calls.

    1. Tier 1: regex patterns (~22 fields)
    2. Tier 3: nutrition table + ingredient block parsers
    3. Tier 2: pattern library lookup for remaining fields (requires db)

    Returns:
        (extraction_dict, confidence_score)
    """
    if not ocr_text or not ocr_text.strip():
        return {}, 0.0

    # Tier 1
    result = _extract_tier1(ocr_text)

    # Tier 3: nutrition table
    if not result["nutritional_table"]:
        nutrition = _parse_nutrition_table(ocr_text)
        if nutrition:
            result["nutritional_table"] = nutrition

    # Tier 3: ingredients
    if not result["ingredient_list"]:
        ingredients = _extract_ingredients(ocr_text)
        if ingredients:
            result["ingredient_list"] = ingredients

    # Tier 2: pattern library (needs db session)
    if db is not None:
        try:
            from app.services.pattern_library import lookup_missing_fields
            result = lookup_missing_fields(result, ocr_text, db)
        except Exception:
            pass  # Non-fatal — pattern library is always optional

    confidence = _calculate_local_confidence(result)
    print(f"[local-extract] confidence={confidence:.3f} "
          f"(filled {sum(1 for f in FIELD_WEIGHTS if _is_filled(result.get(f)))}/"
          f"{len(FIELD_WEIGHTS)} fields)",
          flush=True)

    return result, confidence
