"""
Extraction Service — sends OCR text (or label image directly) to Google Gemini
and extracts a structured JSON representation of the label.

Supports FSSAI, Legal Metrology, and AYUSH regulation fields.
"""

import json
import re
from typing import Optional
from app.config import get_settings

settings = get_settings()

EXTRACTION_PROMPT = """
You are a regulatory compliance expert for Indian packaged goods — specializing in
FSSAI (nutraceuticals, health supplements), Legal Metrology (packaged commodities),
and AYUSH (Ayurvedic/Siddha/Unani drugs).

Analyze the following product label text VERY CAREFULLY and extract ALL information
present into a structured JSON. Read every line of the label text — key information
may be anywhere: front panel, back panel, side panels, footer areas.

IMPORTANT RULES:
- Only set a field to null if the information is genuinely NOT present on the label.
- For boolean fields: set true if the statement/declaration IS present, false only if
  you're certain it's absent after reading the full label.
- For ingredient_list: extract EVERY ingredient mentioned, including "Other Ingredients"
  or excipients like Magnesium Stearate, Silicon Dioxide, etc.
- For warnings: extract ALL warning/advisory/disclaimer text, each as separate list items.
- For health_claims: extract any benefit/function claims like "Improve Endurance", etc.
- For nutritional_table: extract EVERY row from the nutrition facts table.
- For manufacturer_details: include BOTH marketer and manufacturer if both are listed.
- For MRP: look for "MRP", "M.R.P.", or "Maximum Retail Price" declarations.
- For customer_care: look for email addresses, phone numbers, website URLs.

Return ONLY valid JSON with no markdown formatting, no code blocks, just raw JSON.

Required JSON structure:
{
  "product_name": "string or null",
  "product_type_declaration": "string (e.g. 'HEALTH SUPPLEMENT', 'NUTRACEUTICAL', 'AYURVEDIC MEDICINE') or null",
  "fssai_license_number": "14-digit string or null",
  "net_quantity": "string (e.g. '60 Tablets', '500g') or null",
  "serving_size": "string (e.g. '2 tablets', '1 capsule daily') or null",
  "manufacturing_date": "string or null",
  "expiry_date": "string or null",
  "batch_number": "string or null",
  "manufacturer_details": "string (all manufacturer/marketer names + addresses) or null",
  "country_of_origin": "string or null",
  "storage_conditions": "string or null",
  "target_consumer": "string (e.g. 'FOR ADULTS', 'Men & Women') or null",
  "veg_nonveg_mark": "VEG or NON-VEG or null",
  "mrp": "string (e.g. '₹599', 'MRP ₹1299') or null",
  "customer_care_details": "string (email, phone, website) or null",
  "formulation_reference": "string (for AYUSH: authoritative text reference) or null",
  "ingredient_list": ["ingredient 1", "ingredient 2", ...],
  "nutritional_table": [
    {"nutrient": "string", "per_serving": "string", "per_100g": "string or null", "rda_percent": "string or null"}
  ],
  "rda_percentages": true or false,
  "health_claims": ["claim 1", "claim 2"],
  "warnings": ["warning 1", "warning 2", ...],
  "allergen_declarations": ["allergen 1"],
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


def extract_label_data_from_image(image_path: str) -> tuple[dict, float]:
    """
    Send label image directly to Gemini Vision for extraction.
    More accurate than OCR → text → extraction pipeline.
    Falls back to standard OCR pipeline if Vision fails.
    """
    if not settings.gemini_api_key:
        return {}, 0.0

    try:
        import google.generativeai as genai
        from pathlib import Path
        import PIL.Image

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-pro")

        img = PIL.Image.open(image_path)

        vision_prompt = EXTRACTION_PROMPT.replace(
            "Label text to analyze:\n---\n{label_text}\n---",
            "Analyze the product label in this image and extract all information."
        )

        response = model.generate_content(
            [vision_prompt, img],
            generation_config={"temperature": 0.1, "max_output_tokens": 4096},
        )

        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        return result, 0.92

    except Exception as e:
        print(f"[extraction] Gemini Vision failed: {e}")
        return {}, 0.0


def _call_gemini(ocr_text: str) -> Optional[dict]:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = EXTRACTION_PROMPT.format(label_text=ocr_text[:8000])  # token limit safety

    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.1, "max_output_tokens": 4096},
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
    for pt in ["HEALTH SUPPLEMENT", "NUTRACEUTICAL", "FUNCTIONAL FOOD", "NOVEL FOOD", "AYURVEDIC"]:
        if pt.lower() in text_lower:
            product_type = pt
            break

    # Veg/Non-veg
    veg_mark = None
    if re.search(r'\bnon[\s-]?veg\b', text_lower):
        veg_mark = "NON-VEG"
    elif re.search(r'\bveg(?:etarian)?\b', text_lower):
        veg_mark = "VEG"

    # MRP
    mrp_match = re.search(r'(?:MRP|M\.R\.P\.?)[:\s]*[₹Rs\.]*\s*([0-9,]+)', text, re.IGNORECASE)
    mrp = mrp_match.group(0).strip() if mrp_match else None

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
        "mrp": mrp,
        "customer_care_details": None,
        "formulation_reference": None,
        "ingredient_list": [],
        "nutritional_table": [],
        "rda_percentages": has("%rda") or has("% rda") or has("recommended daily"),
        "health_claims": [],
        "warnings": [],
        "allergen_declarations": [],
        "not_for_medicinal_use": has("not for medicinal use"),
        "consult_doctor_advisory": has("consult") and (has("doctor") or has("physician") or has("dietician")),
        "keep_out_of_reach_children": has("out of reach of children"),
        "not_exceed_daily_usage_advisory": has("not to exceed"),
    }
