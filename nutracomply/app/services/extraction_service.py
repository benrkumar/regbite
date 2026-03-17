"""
Extraction Service — sends OCR text to Google Gemini Flash and extracts
a structured JSON representation of the label.
"""

import json
import re
from typing import Optional
from app.config import get_settings

settings = get_settings()

EXTRACTION_PROMPT = """
You are a regulatory expert specializing in FSSAI (Food Safety and Standards Authority of India)
compliance for nutraceutical products.

Analyze the following product label text and extract ALL available information into a structured JSON.
If a field is not present on the label, set it to null.
For list fields (ingredients, health_claims, warnings), return empty lists [] if not found.

Return ONLY valid JSON with no markdown formatting, no code blocks, just raw JSON.

Required JSON structure:
{
  "product_name": "string or null",
  "product_type_declaration": "string (e.g. 'HEALTH SUPPLEMENT', 'NUTRACEUTICAL') or null",
  "fssai_license_number": "14-digit string or null",
  "net_quantity": "string (e.g. '60 capsules', '500g') or null",
  "serving_size": "string (e.g. '1 capsule', '2 tablets') or null",
  "manufacturing_date": "string or null",
  "expiry_date": "string or null",
  "batch_number": "string or null",
  "manufacturer_details": "string (name + address) or null",
  "country_of_origin": "string or null",
  "storage_conditions": "string or null",
  "target_consumer": "string (e.g. 'Adults above 18 years') or null",
  "veg_nonveg_mark": "VEG or NON-VEG or null",
  "ingredient_list": ["ingredient name with quantity if available"],
  "nutritional_table": [
    {"nutrient": "string", "per_serving": "string", "per_100g": "string or null", "rda_percent": "string or null"}
  ],
  "rda_percentages": true or false,
  "health_claims": ["claim 1", "claim 2"],
  "warnings": ["warning 1", "warning 2"],
  "allergen_declarations": ["allergen 1", "allergen 2"],
  "not_for_medicinal_use": true or false,
  "consult_doctor_advisory": true or false,
  "keep_out_of_reach_children": true or false,
  "not_exceed_daily_usage_advisory": true or false
}

Label text to analyze:
---
{label_text}
---
"""


def extract_label_data(ocr_text: str) -> tuple[dict, float]:
    """
    Sends OCR text to Gemini, returns (structured_dict, confidence_score).
    Falls back to rule-based extraction if API call fails.
    """
    if not ocr_text.strip():
        return {}, 0.0

    # Try Gemini API
    if settings.gemini_api_key:
        try:
            result = _call_gemini(ocr_text)
            if result:
                return result, 0.85
        except Exception as e:
            print(f"[extraction] Gemini API failed: {e}")

    # Fallback: rule-based extraction
    return _rule_based_extraction(ocr_text), 0.50


def _call_gemini(ocr_text: str) -> Optional[dict]:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = EXTRACTION_PROMPT.format(label_text=ocr_text[:8000])  # token limit safety

    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.1, "max_output_tokens": 2048},
    )

    raw = response.text.strip()

    # Strip any accidental markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


def _rule_based_extraction(text: str) -> dict:
    """
    Lightweight regex-based extraction as fallback.
    Less accurate but zero API dependency.
    """
    import re

    text_lower = text.lower()

    def find(pattern, group=1):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(group).strip() if m else None

    # FSSAI license number (14 digits)
    fssai_match = re.search(r'\b(\d{14})\b', text)
    fssai_num = fssai_match.group(1) if fssai_match else None

    # Net quantity
    qty_match = re.search(
        r'net\s+(?:quantity|weight|contents?)[:\s]+([^\n,]+)', text, re.IGNORECASE
    )
    net_qty = qty_match.group(1).strip() if qty_match else None

    # Batch number
    batch_match = re.search(r'(?:batch|lot)\s*(?:no\.?|number)[:\s]+([A-Z0-9\-/]+)', text, re.IGNORECASE)
    batch = batch_match.group(1).strip() if batch_match else None

    # Expiry / best before
    expiry_match = re.search(
        r'(?:best before|expiry|use by|exp\.?)[:\s]+([^\n,]+)', text, re.IGNORECASE
    )
    expiry = expiry_match.group(1).strip() if expiry_match else None

    # Mfg date
    mfg_match = re.search(
        r'(?:mfg\.?\s*date|date of mfg|manufactured)[:\s]+([^\n,]+)', text, re.IGNORECASE
    )
    mfg_date = mfg_match.group(1).strip() if mfg_match else None

    # Product type
    product_type = None
    for pt in ["HEALTH SUPPLEMENT", "NUTRACEUTICAL", "FUNCTIONAL FOOD", "NOVEL FOOD"]:
        if pt.lower() in text_lower:
            product_type = pt
            break

    # Veg/Non-veg
    veg_mark = None
    if re.search(r'\bnon[\s-]?veg\b', text_lower):
        veg_mark = "NON-VEG"
    elif re.search(r'\bveg(?:etarian)?\b', text_lower):
        veg_mark = "VEG"

    # Boolean flags
    def has(phrase):
        return phrase.lower() in text_lower

    return {
        "product_name": None,
        "product_type_declaration": product_type,
        "fssai_license_number": fssai_num,
        "net_quantity": net_qty,
        "serving_size": None,
        "manufacturing_date": mfg_date,
        "expiry_date": expiry,
        "batch_number": batch,
        "manufacturer_details": None,
        "country_of_origin": None,
        "storage_conditions": None,
        "target_consumer": None,
        "veg_nonveg_mark": veg_mark,
        "ingredient_list": [],
        "nutritional_table": [],
        "rda_percentages": has("%rda") or has("% rda") or has("recommended daily"),
        "health_claims": [],
        "warnings": [],
        "allergen_declarations": [],
        "not_for_medicinal_use": has("not for medicinal use"),
        "consult_doctor_advisory": has("consult") and (has("doctor") or has("physician")),
        "keep_out_of_reach_children": has("out of reach of children"),
        "not_exceed_daily_usage_advisory": has("not to exceed"),
    }
