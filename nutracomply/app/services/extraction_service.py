"""
Extraction Service — sends label image or OCR text to an LLM
and extracts a structured JSON representation of the label.

Supports FSSAI, Legal Metrology, and AYUSH regulation fields.

v4 improvements:
  - Primary: Anthropic Claude (Sonnet) via direct HTTP — no SDK dependency
  - Fallback: Google Gemini if Claude unavailable
  - Dynamic confidence scoring based on field completeness
  - Post-extraction OCR cross-check for accuracy
  - Post-extraction validation with missing-field warnings
"""

import base64
import io
import json
import re
from pathlib import Path
from typing import Optional
from app.config import get_settings

settings = get_settings()

# ─── Critical fields that heavily affect compliance scoring ──────────────────
CRITICAL_FIELDS = [
    "product_name", "product_type_declaration", "fssai_license_number",
    "net_quantity", "expiry_date", "manufacturer_details", "ingredient_list",
]
IMPORTANT_FIELDS = [
    "serving_size", "manufacturing_date", "batch_number", "storage_conditions",
    "veg_nonveg_mark", "mrp", "nutritional_table", "warnings",
]
ALL_EXPECTED_FIELDS = [
    "product_name", "product_type_declaration", "fssai_license_number",
    "net_quantity", "serving_size", "manufacturing_date", "expiry_date",
    "batch_number", "manufacturer_details", "country_of_origin",
    "storage_conditions", "target_consumer", "veg_nonveg_mark", "mrp",
    "customer_care_details", "formulation_reference", "ingredient_list",
    "nutritional_table", "rda_percentages", "health_claims", "warnings",
    "allergen_declarations", "not_for_medicinal_use", "consult_doctor_advisory",
    "keep_out_of_reach_children", "not_exceed_daily_usage_advisory",
]

EXTRACTION_PROMPT = """
You are a regulatory compliance expert for Indian packaged goods — specializing in
FSSAI (nutraceuticals, health supplements), Legal Metrology (packaged commodities),
and AYUSH (Ayurvedic/Siddha/Unani drugs).

Analyze the following product label VERY CAREFULLY and extract ALL information
present into a structured JSON. Read every line — key information may be anywhere:
front panel, back panel, side panels, footer areas, cap/lid text.

IMPORTANT RULES:
- Only set a field to null if the information is genuinely NOT present on the label.
- For boolean fields: set true if the statement/declaration IS present, false only if
  you're certain it's absent after reading the full label.
- For ingredient_list: extract EVERY ingredient mentioned, including "Other Ingredients"
  or excipients like Magnesium Stearate, Silicon Dioxide, HPMC capsule shells, etc.
  Include dosages/amounts if printed (e.g. "Ashwagandha Extract 500mg").
- For warnings: extract ALL warning/advisory/disclaimer text, each as separate list items.
  Include "Not for medicinal use", "Consult doctor", "Keep out of reach" etc.
- For health_claims: extract any benefit/function claims like "Improve Endurance",
  "Supports joint health", etc. Include the EXACT wording from the label.
- For nutritional_table: extract EVERY row from the nutrition facts table.
  Include units (mg, mcg, IU, etc.) in per_serving and per_100g values.
- For manufacturer_details: include BOTH marketer and manufacturer if both are listed.
  Include full addresses, license numbers, contact info.
- For MRP: look for "MRP", "M.R.P.", or "Maximum Retail Price" declarations.
  Include "inclusive of all taxes" if stated.
- For customer_care: look for email addresses, phone numbers, website URLs, toll-free numbers.
- For allergen_declarations: look for "Contains:", "May contain:", allergen boxes/panels.
- For formulation_reference: AYUSH products cite texts like AFI, API, Charaka Samhita — extract the reference.

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
  "mrp": "string (e.g. '₹599', 'MRP ₹1299 inclusive of all taxes') or null",
  "customer_care_details": "string (email, phone, website) or null",
  "formulation_reference": "string (for AYUSH: authoritative text reference) or null",
  "ingredient_list": ["ingredient 1 with amount if shown", "ingredient 2", ...],
  "nutritional_table": [
    {"nutrient": "string", "per_serving": "string with unit", "per_100g": "string or null", "rda_percent": "string or null"}
  ],
  "rda_percentages": true or false,
  "health_claims": ["exact claim text 1", "exact claim text 2"],
  "warnings": ["warning 1", "warning 2", ...],
  "allergen_declarations": ["allergen 1"],
  "not_for_medicinal_use": true or false,
  "consult_doctor_advisory": true or false,
  "keep_out_of_reach_children": true or false,
  "not_exceed_daily_usage_advisory": true or false
}
"""

VISION_PROMPT = EXTRACTION_PROMPT + """
Analyze the product label in this image. Look at ALL visible panels — front, back,
sides, top, bottom. Zoom into fine print areas for batch numbers, FSSAI license,
manufacturing dates, and warnings. If text is partially obscured or blurry, extract
what you can read and note uncertainty in the value (e.g. "Batch: B2024-0?? (partially obscured)").
"""

MULTI_PAGE_VISION_PROMPT = EXTRACTION_PROMPT + """
You are looking at MULTIPLE PAGES/IMAGES of the SAME product label.
Information may be spread across pages (front panel, back panel, side panels, inserts).
Combine ALL information from ALL pages into a single unified JSON.
If the same field appears on multiple pages, prefer the most complete/detailed version.
Look at EVERY page carefully — key regulatory info (FSSAI number, batch, expiry, warnings)
is often on back/side panels that appear in later pages.
"""

TEXT_PROMPT = EXTRACTION_PROMPT + """
Label text to analyze:
---
{label_text}
---
"""


def _calculate_confidence(extraction: dict, source: str) -> float:
    """
    Calculate dynamic confidence score based on field completeness.
    Source: 'vision' (base 0.90), 'text' (base 0.82), 'fallback' (base 0.40).
    Adjusts ±0.10 based on how many critical/important fields were extracted.
    """
    base_scores = {"vision": 0.90, "text": 0.82, "fallback": 0.40}
    base = base_scores.get(source, 0.50)

    if not extraction:
        return 0.0

    # Critical fields: each missing one drops confidence significantly
    critical_present = 0
    for f in CRITICAL_FIELDS:
        val = extraction.get(f)
        if val and val is not True and val != []:
            critical_present += 1
        elif val is True:  # boolean field
            critical_present += 1
    critical_ratio = critical_present / len(CRITICAL_FIELDS)

    # Important fields: secondary weight
    important_present = 0
    for f in IMPORTANT_FIELDS:
        val = extraction.get(f)
        if val and val is not True and val != []:
            important_present += 1
        elif val is True:
            important_present += 1
    important_ratio = important_present / len(IMPORTANT_FIELDS)

    # Weighted adjustment: critical fields matter 3x more
    completeness = (critical_ratio * 0.75 + important_ratio * 0.25)
    # Adjust confidence: ±0.10 from base
    confidence = base + (completeness - 0.5) * 0.20
    return round(max(0.10, min(0.99, confidence)), 2)


def _validate_extraction(extraction: dict) -> list[str]:
    """
    Post-extraction validation. Returns list of warning messages
    about missing or suspicious fields.
    """
    warnings = []

    # Check for missing critical fields
    for f in CRITICAL_FIELDS:
        val = extraction.get(f)
        if val is None or val == "" or val == []:
            warnings.append(f"Critical field '{f}' not found on label")

    # FSSAI license format validation
    fssai = extraction.get("fssai_license_number")
    if fssai and not re.match(r'^\d{14}$', str(fssai).strip()):
        warnings.append(f"FSSAI license '{fssai}' doesn't match expected 14-digit format")

    # Ingredient list sanity check
    ingredients = extraction.get("ingredient_list", [])
    if isinstance(ingredients, list) and len(ingredients) == 1:
        # Might be a comma-separated string that wasn't split
        if "," in ingredients[0]:
            warnings.append("Ingredient list may not be properly split (single item with commas)")

    # Nutritional table sanity check
    nt = extraction.get("nutritional_table", [])
    if isinstance(nt, list) and len(nt) > 0:
        for row in nt[:3]:  # spot-check first 3 rows
            if isinstance(row, dict) and not row.get("per_serving"):
                warnings.append("Nutritional table has rows missing 'per_serving' values")
                break

    return warnings


# ─── PDF to images ─────────────────────────────────────────────────────────

def _pdf_to_images(pdf_path: str, dpi: int = 300) -> list[tuple[bytes, str]]:
    """Convert PDF pages to PNG images. Returns list of (image_bytes, media_type)."""
    import fitz  # PyMuPDF

    images = []
    doc = fitz.open(pdf_path)
    for page_num in range(min(len(doc), 10)):  # cap at 10 pages
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        images.append((img_bytes, "image/png"))
    doc.close()
    return images


# ─── Claude (Anthropic) via direct HTTP ───────────────────────────────────

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_VERSION = "2023-06-01"


def _claude_request(messages: list, max_tokens: int = 8192) -> Optional[str]:
    """Make a direct HTTP call to the Anthropic Messages API."""
    import httpx

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": CLAUDE_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    resp = httpx.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=120.0)
    if resp.status_code != 200:
        print(f"[claude-api] HTTP {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()
    print(f"[claude-api] OK — model={data.get('model')}, tokens={data.get('usage')}")
    return data["content"][0]["text"].strip()


def _parse_json_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_claude_vision(image_path: str) -> Optional[dict]:
    """Use Claude Vision via direct HTTP to extract label data from an image or PDF."""
    img_path = Path(image_path)
    suffix = img_path.suffix.lower()

    # For PDFs, convert to images and send all pages
    if suffix == ".pdf":
        return _call_claude_vision_multi(image_path)

    # Single image
    image_data = img_path.read_bytes()
    b64_image = base64.b64encode(image_data).decode("utf-8")

    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif", ".tiff": "image/tiff", ".tif": "image/tiff",
    }
    media_type = media_types.get(suffix, "image/jpeg")

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_image,
                },
            },
            {"type": "text", "text": VISION_PROMPT},
        ],
    }]

    raw = _claude_request(messages)
    return _parse_json_response(raw)


def _call_claude_vision_multi(pdf_path: str) -> Optional[dict]:
    """Send all PDF pages as images to Claude for combined extraction."""
    pages = _pdf_to_images(pdf_path)
    if not pages:
        return None

    content_blocks = []
    for img_bytes, media_type in pages:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })

    prompt = MULTI_PAGE_VISION_PROMPT if len(pages) > 1 else VISION_PROMPT
    content_blocks.append({"type": "text", "text": prompt})

    messages = [{"role": "user", "content": content_blocks}]
    raw = _claude_request(messages)
    return _parse_json_response(raw)


def _call_claude_text(ocr_text: str) -> Optional[dict]:
    """Use Claude text via direct HTTP to extract label data from OCR text."""
    prompt = TEXT_PROMPT.format(label_text=ocr_text[:16000])

    messages = [{"role": "user", "content": prompt}]
    raw = _claude_request(messages)
    return _parse_json_response(raw)


# ─── Gemini fallback ────────────────────────────────────────────────────────

def _call_gemini_vision(image_path: str) -> Optional[dict]:
    """Fallback: Gemini Vision for image/PDF extraction."""
    import google.generativeai as genai
    import PIL.Image

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-pro-preview-06-05")

    img_path = Path(image_path)
    suffix = img_path.suffix.lower()

    if suffix == ".pdf":
        # Convert PDF to images for Gemini
        pages = _pdf_to_images(image_path, dpi=200)
        if not pages:
            return None
        pil_images = []
        for img_bytes, _ in pages:
            pil_images.append(PIL.Image.open(io.BytesIO(img_bytes)))
        prompt = MULTI_PAGE_VISION_PROMPT if len(pil_images) > 1 else VISION_PROMPT
        response = model.generate_content(
            pil_images + [prompt],
            generation_config={"temperature": 0.1, "max_output_tokens": 8192},
        )
    else:
        img = PIL.Image.open(image_path)
        response = model.generate_content(
            [VISION_PROMPT, img],
            generation_config={"temperature": 0.1, "max_output_tokens": 8192},
        )

    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_gemini_text(ocr_text: str) -> Optional[dict]:
    """Fallback: Gemini text for OCR-based extraction."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = TEXT_PROMPT.format(label_text=ocr_text[:12000])

    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.1, "max_output_tokens": 8192},
    )

    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ─── Public API ─────────────────────────────────────────────────────────────

def extract_label_data_from_image(image_path: str) -> tuple[dict, float]:
    """
    Extract structured label data from an image file.
    Primary: Claude Vision → Fallback: Gemini Vision
    """
    # Try Claude first
    if settings.anthropic_api_key:
        try:
            result = _call_claude_vision(image_path)
            if result:
                result = _normalize_extraction(result)
                confidence = _calculate_confidence(result, "vision")
                warnings = _validate_extraction(result)
                if warnings:
                    result["_extraction_warnings"] = warnings
                    print(f"[extraction] Claude Vision warnings: {warnings}")
                print(f"[extraction] Claude Vision succeeded (confidence={confidence})")
                return result, confidence
        except Exception as e:
            print(f"[extraction] Claude Vision failed: {e}")

    # Fallback: Gemini Vision
    if settings.gemini_api_key:
        try:
            result = _call_gemini_vision(image_path)
            if result:
                result = _normalize_extraction(result)
                confidence = _calculate_confidence(result, "vision")
                warnings = _validate_extraction(result)
                if warnings:
                    result["_extraction_warnings"] = warnings
                    print(f"[extraction] Gemini Vision warnings: {warnings}")
                print(f"[extraction] Gemini Vision fallback succeeded (confidence={confidence})")
                return result, confidence
        except Exception as e:
            print(f"[extraction] Gemini Vision fallback failed: {e}")

    return {}, 0.0


def extract_label_data(ocr_text: str) -> tuple[dict, float]:
    """
    Extract structured label data from OCR text.
    Primary: Claude Text → Fallback: Gemini Text → Fallback: Rule-based
    """
    if not ocr_text.strip():
        return {}, 0.0

    # Try Claude first
    if settings.anthropic_api_key:
        try:
            result = _call_claude_text(ocr_text)
            if result:
                result = _normalize_extraction(result)
                result = _cross_check_with_ocr(result, ocr_text)
                confidence = _calculate_confidence(result, "text")
                warnings = _validate_extraction(result)
                if warnings:
                    result["_extraction_warnings"] = warnings
                    print(f"[extraction] Claude text warnings: {warnings}")
                print(f"[extraction] Claude text succeeded (confidence={confidence})")
                return result, confidence
        except Exception as e:
            print(f"[extraction] Claude text failed: {e}")

    # Fallback: Gemini
    if settings.gemini_api_key:
        try:
            result = _call_gemini_text(ocr_text)
            if result:
                result = _normalize_extraction(result)
                result = _cross_check_with_ocr(result, ocr_text)
                confidence = _calculate_confidence(result, "text")
                warnings = _validate_extraction(result)
                if warnings:
                    result["_extraction_warnings"] = warnings
                    print(f"[extraction] Gemini text warnings: {warnings}")
                return result, confidence
        except Exception as e:
            print(f"[extraction] Gemini text failed: {e}")

    # Final fallback: rule-based extraction
    fallback = _rule_based_extraction(ocr_text)
    confidence = _calculate_confidence(fallback, "fallback")
    return fallback, confidence


def _cross_check_with_ocr(extraction: dict, ocr_text: str) -> dict:
    """
    Post-extraction OCR cross-check. Compares AI extraction against raw OCR text
    and fixes fields where the OCR clearly contains information the AI missed.
    This catches cases where the LLM returns false/null for fields that ARE present.
    """
    if not ocr_text or not extraction:
        return extraction

    text = ocr_text
    text_lower = text.lower()

    # Boolean field fixes — only upgrade from False to True, never downgrade
    if not extraction.get("not_for_medicinal_use"):
        if "not for medicinal use" in text_lower:
            extraction["not_for_medicinal_use"] = True
            print("[ocr-crosscheck] Fixed not_for_medicinal_use → True")

    if not extraction.get("consult_doctor_advisory"):
        if "consult" in text_lower and any(
            w in text_lower for w in ("doctor", "dietitian", "physician", "healthcare")
        ):
            extraction["consult_doctor_advisory"] = True
            print("[ocr-crosscheck] Fixed consult_doctor_advisory → True")

    if not extraction.get("keep_out_of_reach_children"):
        if "out of reach" in text_lower and "children" in text_lower:
            extraction["keep_out_of_reach_children"] = True
            print("[ocr-crosscheck] Fixed keep_out_of_reach_children → True")

    if not extraction.get("not_exceed_daily_usage_advisory"):
        has_exceed = "not to exceed" in text_lower or "not exceed" in text_lower
        has_daily = "daily" in text_lower or "recommended" in text_lower
        if has_exceed and has_daily:
            extraction["not_exceed_daily_usage_advisory"] = True
            print("[ocr-crosscheck] Fixed not_exceed_daily_usage_advisory → True")

    # Veg/non-veg mark
    if not extraction.get("veg_nonveg_mark"):
        if re.search(r'\bvegetarian\b', text_lower) or re.search(r'\bveg\b', text_lower):
            extraction["veg_nonveg_mark"] = "VEG"
            print("[ocr-crosscheck] Fixed veg_nonveg_mark → VEG")

    # FSSAI license number (14-digit number)
    if not extraction.get("fssai_license_number"):
        fssai_match = re.search(r'\b(\d{14})\b', text)
        if fssai_match:
            extraction["fssai_license_number"] = fssai_match.group(1)
            print(f"[ocr-crosscheck] Fixed fssai_license_number → {fssai_match.group(1)}")

    # Manufacturer details
    if not extraction.get("manufacturer_details"):
        mfg_match = re.search(r'(?:manufactured\s+by|marketed\s+by)', text_lower)
        if mfg_match:
            start = mfg_match.start()
            snippet = text[start:start + 200].strip()
            extraction["manufacturer_details"] = snippet
            print(f"[ocr-crosscheck] Fixed manufacturer_details from OCR")

    # Net quantity
    if not extraction.get("net_quantity"):
        qty_match = re.search(
            r'(?:net\s+(?:wt\.?|weight|qty\.?|quantity)[:\s]*)([\d.,]+\s*(?:g|mg|kg|ml|l|tablets?|capsules?|softgels?))',
            text, re.IGNORECASE
        )
        if qty_match:
            extraction["net_quantity"] = qty_match.group(0).strip()
            print(f"[ocr-crosscheck] Fixed net_quantity → {extraction['net_quantity']}")

    # Serving size
    if not extraction.get("serving_size"):
        srv_match = re.search(r'serving\s+size[:\s]*([^\n]{5,80})', text, re.IGNORECASE)
        if srv_match:
            extraction["serving_size"] = srv_match.group(1).strip()
            print(f"[ocr-crosscheck] Fixed serving_size from OCR")

    # Storage conditions
    if not extraction.get("storage_conditions"):
        store_match = re.search(r'store[:\s]', text_lower)
        if store_match and any(w in text_lower for w in ("cool", "dry", "sunlight")):
            # Extract the sentence containing "store"
            start = max(0, store_match.start() - 10)
            # Find the end of the sentence
            end = store_match.end()
            for i in range(end, min(len(text), end + 200)):
                if text[i] in '.!\n':
                    end = i + 1
                    break
            else:
                end = min(len(text), store_match.start() + 200)
            extraction["storage_conditions"] = text[start:end].strip()
            print(f"[ocr-crosscheck] Fixed storage_conditions from OCR")

    # Allergen declarations
    allergens = extraction.get("allergen_declarations", [])
    if not allergens or allergens == []:
        if "allergen" in text_lower:
            allerg_match = re.search(r'allergen[s]?[:\s]*([^\n]{5,200})', text, re.IGNORECASE)
            if allerg_match:
                extraction["allergen_declarations"] = [allerg_match.group(1).strip()]
                print(f"[ocr-crosscheck] Fixed allergen_declarations from OCR")

    # MRP
    if not extraction.get("mrp"):
        mrp_match = re.search(r'(?:MRP|M\.R\.P\.?)[:\s]*[₹Rs\.]*\s*([0-9,]+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if mrp_match:
            extraction["mrp"] = mrp_match.group(0).strip()
            print(f"[ocr-crosscheck] Fixed mrp → {extraction['mrp']}")

    # Customer care details (email or phone)
    if not extraction.get("customer_care_details"):
        email_match = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
        phone_match = re.search(r'(?:\+91[\s\-]?)?(?:\d[\s\-]?){10,12}', text)
        if email_match:
            extraction["customer_care_details"] = email_match.group(0)
            print(f"[ocr-crosscheck] Fixed customer_care_details (email) from OCR")
        elif phone_match:
            extraction["customer_care_details"] = phone_match.group(0).strip()
            print(f"[ocr-crosscheck] Fixed customer_care_details (phone) from OCR")

    return extraction


def _normalize_extraction(data: dict) -> dict:
    """
    Post-process extraction to fix common LLM output quirks:
    - Split comma-joined ingredient lists
    - Ensure all expected fields exist (fill missing with None/[]/False)
    - Strip whitespace from string values
    """
    # Ensure all expected fields present
    for field in ALL_EXPECTED_FIELDS:
        if field not in data:
            if field in ("ingredient_list", "nutritional_table", "health_claims",
                        "warnings", "allergen_declarations"):
                data[field] = []
            elif field in ("rda_percentages", "not_for_medicinal_use",
                          "consult_doctor_advisory", "keep_out_of_reach_children",
                          "not_exceed_daily_usage_advisory"):
                data[field] = False
            else:
                data[field] = None

    # Fix ingredient list: sometimes LLM returns single comma-separated string
    ingredients = data.get("ingredient_list", [])
    if isinstance(ingredients, list) and len(ingredients) == 1 and "," in str(ingredients[0]):
        data["ingredient_list"] = [i.strip() for i in str(ingredients[0]).split(",") if i.strip()]

    # Strip whitespace from string fields
    for key, val in data.items():
        if isinstance(val, str):
            data[key] = val.strip()

    return data


def _rule_based_extraction(text: str) -> dict:
    """
    Lightweight regex-based extraction as fallback.
    Less accurate but zero API dependency.
    """
    text_lower = text.lower()

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
