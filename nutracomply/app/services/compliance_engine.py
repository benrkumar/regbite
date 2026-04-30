"""
Compliance Engine — runs all active rules against an extracted label JSON.
Covers FSSAI, Legal Metrology, and AYUSH (ASU) regulations.
Returns a list of ComplianceCheck results with PASS/FAIL/WARNING + remediation.

v2 improvements:
  - Severity-weighted compliance scoring (CRITICAL=4x, HIGH=3x, MEDIUM=2x, LOW=1x)
  - LLM-assisted FORMAT checks (verifies format via Gemini instead of blanket WARNING)
  - Smarter field normalization before comparisons
"""

import logging
import re
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models import ComplianceRule, ComplianceCheck, LabelVersion, CheckType, CheckResult, Severity


# ─── Deterministic helper utilities ──────────────────────────────────────────

def _norm(text) -> str:
    """Lowercase, strip and collapse whitespace for fast substring comparison."""
    return " ".join(str(text).lower().split())


def _concat(extraction: dict, *fields: str) -> str:
    """Concatenate multiple extraction fields into one searchable lowercase string."""
    parts: list[str] = []
    for f in fields:
        val = extraction.get(f)
        if isinstance(val, list):
            parts.extend(str(v) for v in val)
        elif val is not None:
            parts.append(str(val))
    return _norm(" ".join(parts))

# Severity weights for compliance scoring — not all rules are equal
SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
}


def run_compliance_check(label_version: LabelVersion, db: Session) -> list[ComplianceCheck]:
    """
    Runs applicable active rules against the label_version's extraction_json.
    Rules are filtered by product category:
      - FSSAI-NUTRA rules → all food/supplement categories
      - LM-PKG rules → all packaged products
      - AYUSH-ASU rules → only "Ayurvedic / ASU" category
    Saves and returns ComplianceCheck records.
    """
    extraction = label_version.extraction_json or {}
    all_rules = db.query(ComplianceRule).filter(ComplianceRule.active).all()

    # Filter rules by product category and framework
    product_category = (label_version.product.category or "").lower().strip()
    # All products under the Ministry of AYUSH — Ayurvedic, Siddha, Unani, and
    # Ayurveda Aahara food categories — must pass AYUSH-prefixed rules.
    _AYUSH_KEYWORDS = {"ayurvedic", "ayurveda", "asu", "siddha", "unani", "ayush"}
    is_ayurvedic = any(kw in product_category for kw in _AYUSH_KEYWORDS)
    is_imported = bool(
        extraction.get("country_of_origin")
        and "india" not in str(extraction.get("country_of_origin", "")).lower()
    )

    # Sub-category rules only apply when the product matches the sub-category.
    # Combines product.category and extraction product_type_declaration for matching.
    _SUBCATEGORY_PREFIXES = {
        "FSSAI-SPT-":  {"sports", "sportsperson", "sport nutrition"},
        "FSSAI-FSMP-": {"fsmp", "food for special medical purpose", "special medical"},
        "FSSAI-PROB-": {"probiotic"},
        "FSSAI-BOT-":  {"botanical", "herbal extract", "plant extract"},
        "FSSAI-FRT-":  {"fortified"},
        "FSSAI-VGN-":  {"vegan"},
        "FSSAI-CHN-":  {"children", "child", "infant", "paediatric", "pediatric"},
        "FSSAI-SDU-":  {"weight management", "slimming", "dietary use"},
        "AYUSH-AA-":   {"ayurveda aahara", "ayush aahara"},
    }
    _ptd = (extraction.get("product_type_declaration") or "").lower()
    _combined_cat = f"{product_category} {_ptd}"

    rules = []
    for rule in all_rules:
        code = rule.rule_code or ""
        # AYUSH-ASU rules only apply to Ayurvedic/ASU products
        if code.startswith("AYUSH-") and not is_ayurvedic:
            # Allow AYUSH-AA- rules through if they match sub-category keywords
            if not code.startswith("AYUSH-AA-"):
                continue
        # DGFT import rules only apply to imported products
        if code.startswith("DGFT-") and not is_imported:
            continue
        # Sub-category rules only apply to matching product types
        skip = False
        for prefix, keywords in _SUBCATEGORY_PREFIXES.items():
            if code.startswith(prefix):
                if not any(kw in _combined_cat for kw in keywords):
                    skip = True
                break
        if skip:
            continue
        rules.append(rule)

    # Delete previous checks for this label version
    db.query(ComplianceCheck).filter(
        ComplianceCheck.label_version_id == label_version.id
    ).delete()

    # ── Separate FORMAT rules — processed in one batched LLM call ─────────────
    _FORMAT_TYPES = {CheckType.FORMAT, CheckType.FORMAT_LLM}
    format_rules = [r for r in rules if r.check_type in _FORMAT_TYPES]
    other_rules  = [r for r in rules if r.check_type not in _FORMAT_TYPES]

    checks = []
    # Non-FORMAT rules: fast regex / presence / list checks (no API calls)
    for rule in other_rules:
        check = _evaluate_rule(rule, extraction, label_version.id)
        db.add(check)
        checks.append(check)

    # FORMAT rules: deterministic handlers first, remainder to LLM batch
    deterministic_rules = [r for r in format_rules if r.rule_code in _DETERMINISTIC_FORMAT_HANDLERS]
    llm_format_rules    = [r for r in format_rules if r.rule_code not in _DETERMINISTIC_FORMAT_HANDLERS]

    for rule in deterministic_rules:
        handler = _DETERMINISTIC_FORMAT_HANDLERS[rule.rule_code]
        try:
            result, actual_value, message = handler(extraction)
        except Exception as exc:
            logger.warning(
                "[compliance] Deterministic handler failed for %s: %s — routing to LLM",
                rule.rule_code, exc,
            )
            llm_format_rules.append(rule)
            continue
        check = ComplianceCheck(
            label_version_id=label_version.id,
            rule_id=rule.id,
            result=result,
            actual_value=str(actual_value)[:500] if actual_value else None,
            message=message,
            remediation=(
                rule.remediation_template or ""
                if result in (CheckResult.FAIL, CheckResult.WARNING)
                else None
            ),
        )
        db.add(check)
        checks.append(check)

    if llm_format_rules:
        logger.debug("[compliance] FORMAT rules: %d deterministic, %d to LLM batch",
                     len(deterministic_rules), len(llm_format_rules))
        batch_checks = _check_format_rules_batch(llm_format_rules, extraction, label_version.id)
        for check in batch_checks:
            db.add(check)
        checks.extend(batch_checks)

    db.commit()
    return checks


def _evaluate_rule(rule: ComplianceRule, extraction: dict, label_version_id: int) -> ComplianceCheck:
    config = rule.check_config or {}
    result = CheckResult.SKIPPED
    actual_value = None
    message = ""
    remediation = rule.remediation_template or ""

    try:
        if rule.check_type == CheckType.PRESENCE:
            result, actual_value, message = _check_presence(rule, config, extraction)

        elif rule.check_type == CheckType.ABSENCE:
            result, actual_value, message = _check_absence(rule, config, extraction)

        elif rule.check_type == CheckType.PATTERN_MATCH:
            result, actual_value, message = _check_pattern(rule, config, extraction)

        elif rule.check_type == CheckType.NOT_IN_LIST:
            result, actual_value, message = _check_not_in_list(rule, config, extraction)

        elif rule.check_type == CheckType.VALUE_IN_LIST:
            result, actual_value, message = _check_value_in_list(rule, config, extraction)

        elif rule.check_type in (CheckType.FORMAT, CheckType.FORMAT_LLM):
            result, actual_value, message = _check_format_llm(rule, config, extraction)

    except Exception as e:
        result = CheckResult.SKIPPED
        message = f"Check error: {e}"

    return ComplianceCheck(
        label_version_id=label_version_id,
        rule_id=rule.id,
        result=result,
        actual_value=str(actual_value)[:500] if actual_value else None,
        message=message,
        remediation=remediation if result in (CheckResult.FAIL, CheckResult.WARNING) else None,
    )


# ─── Check implementations ───────────────────────────────────────────────────

def _check_presence(rule: ComplianceRule, config: dict, extraction: dict):
    field = config.get("field")
    if not field:
        return CheckResult.SKIPPED, None, "No field specified in rule config"

    # Handle conditional applicability (e.g. "applies_to": "imported_products")
    applies_to = config.get("applies_to")
    if applies_to == "imported_products":
        # Only enforce for imported products; skip for domestic or unknown
        country = extraction.get("country_of_origin", "")
        if not country or "india" in str(country).lower():
            return CheckResult.PASS, "Domestic product", "Country of origin check — not applicable (domestic product)"

    value = extraction.get(field)

    # Boolean fields (e.g. not_for_medicinal_use)
    if isinstance(value, bool):
        if value:
            return CheckResult.PASS, "true", f"'{field}' is confirmed present on label"
        else:
            return CheckResult.FAIL, "false", "Required statement not found on label"

    # Required text pattern within a list of strings (or any string field)
    required_text = config.get("required_text")
    if required_text:
        if isinstance(value, list):
            combined = " ".join(str(v).lower() for v in value)
        elif isinstance(value, str):
            combined = value.lower()
        else:
            combined = ""

        if required_text.lower() in combined:
            return CheckResult.PASS, required_text, f"Required text '{required_text}' found"

        # Cross-check: for "NOT FOR MEDICINAL USE" also check the boolean field
        rt_lower = required_text.lower()
        if "not for medicinal use" in rt_lower and extraction.get("not_for_medicinal_use") is True:
            return CheckResult.PASS, "not_for_medicinal_use=true", f"'{required_text}' confirmed via boolean field"
        if "not to exceed" in rt_lower and extraction.get("not_exceed_daily_usage_advisory") is True:
            return CheckResult.PASS, "not_exceed_daily_usage_advisory=true", f"'{required_text}' confirmed via boolean field"
        if "consult" in rt_lower and ("doctor" in rt_lower or "physician" in rt_lower) and extraction.get("consult_doctor_advisory") is True:
            return CheckResult.PASS, "consult_doctor_advisory=true", f"'{required_text}' confirmed via boolean field"

        if not combined:
            return CheckResult.FAIL, None, f"Required text '{required_text}' not found — field '{field}' is empty"
        return CheckResult.FAIL, None, f"Required text '{required_text}' not found in {field}"

    # Allowed values
    allowed_values = config.get("allowed_values")
    if allowed_values and isinstance(value, str):
        for av in allowed_values:
            if av.lower() in value.lower():
                return CheckResult.PASS, value, f"Valid product type declaration found: '{value}'"
        return CheckResult.FAIL, value, f"Product type declaration must be one of: {allowed_values}"

    # Allergen declarations: empty list is acceptable if product may not contain allergens
    if field == "allergen_declarations" and isinstance(value, list) and len(value) == 0:
        # Check if any known allergens appear in the ingredient list
        ingredients = extraction.get("ingredient_list", [])
        common_allergens = config.get("common_allergens", [])
        if ingredients and common_allergens:
            ing_text = " ".join(str(i).lower() for i in ingredients)
            found = [a for a in common_allergens if a.lower() in ing_text]
            if found:
                return CheckResult.FAIL, str(found), f"Possible allergens found in ingredients ({found}) but no allergen declaration"
        return CheckResult.PASS, "No allergens detected", "No allergen declaration needed — no common allergens found in ingredients"

    # Minimum items check (e.g. nutritional_table must have >= N rows)
    min_items = config.get("min_items")
    if min_items and isinstance(value, list):
        if len(value) >= min_items:
            return CheckResult.PASS, f"{len(value)} items", f"'{field}' has {len(value)} entries (minimum {min_items})"
        else:
            return CheckResult.FAIL, f"{len(value)} items", f"'{field}' has {len(value)} entries but requires at least {min_items}"

    # Required nutrient in nutritional table (e.g. must have "energy" row)
    required_nutrient = config.get("required_nutrient")
    if required_nutrient and field == "nutritional_table" and isinstance(value, list):
        if not value:
            return CheckResult.FAIL, None, f"Nutritional table is empty — '{required_nutrient}' not declared"
        # Normalise: lowercase + replace underscores with spaces so
        # "added_sugars" matches "Added Sugars", "total_fat" matches "Total Fat", etc.
        def _norm(s: str) -> str:
            return s.lower().replace("_", " ").replace("-", " ")
        nutrient_names = " | ".join(
            _norm(str(row.get("nutrient", ""))) for row in value if isinstance(row, dict)
        )
        needle = _norm(required_nutrient)
        if needle in nutrient_names:
            return CheckResult.PASS, required_nutrient, f"Required nutrient '{required_nutrient}' found in nutritional table"
        else:
            return CheckResult.FAIL, None, f"Required nutrient '{required_nutrient}' not found in nutritional table"

    # Simple non-empty check
    if value and (not isinstance(value, (list, dict)) or len(value) > 0):
        display = str(value)[:100] if not isinstance(value, list) else f"{len(value)} items"
        return CheckResult.PASS, display, f"'{field}' is present on label"
    else:
        return CheckResult.FAIL, None, f"Required field '{field}' is missing or empty on label"


def _check_absence(rule: ComplianceRule, config: dict, extraction: dict):
    field = config.get("field")
    prohibited_patterns = config.get("prohibited_patterns", [])

    if not field or not prohibited_patterns:
        return CheckResult.SKIPPED, None, "Incomplete rule config"

    value = extraction.get(field, [])
    # Combine all text in the field
    if isinstance(value, list):
        combined_text = " ".join(str(v).lower() for v in value)
    else:
        combined_text = str(value).lower() if value else ""

    if not combined_text:
        return CheckResult.PASS, None, f"No content in '{field}' — prohibited claims not detected"

    violations = []
    for pattern in prohibited_patterns:
        matches = re.findall(pattern, combined_text, re.IGNORECASE)
        if matches:
            violations.extend(matches)

    if violations:
        return (
            CheckResult.FAIL,
            str(violations[:3]),
            f"Prohibited language detected in '{field}': {violations[:3]}"
        )
    return CheckResult.PASS, None, f"No prohibited claims detected in '{field}'"


def _check_pattern(rule: ComplianceRule, config: dict, extraction: dict):
    field = config.get("field")
    pattern = config.get("pattern")

    if not field or not pattern:
        return CheckResult.SKIPPED, None, "Incomplete rule config"

    value = extraction.get(field)
    if not value:
        return CheckResult.FAIL, None, f"Field '{field}' is missing"

    if re.match(pattern, str(value)):
        return CheckResult.PASS, str(value), f"'{field}' matches required format"
    else:
        return (
            CheckResult.FAIL,
            str(value),
            f"'{field}' value '{value}' does not match required format: {config.get('description', pattern)}"
        )


def _check_not_in_list(rule: ComplianceRule, config: dict, extraction: dict):
    field = config.get("field")
    banned_items = [b.lower() for b in config.get("banned_items", [])]

    if not field or not banned_items:
        return CheckResult.SKIPPED, None, "Incomplete rule config"

    ingredients = extraction.get(field, [])
    if not isinstance(ingredients, list):
        return CheckResult.SKIPPED, None, "Ingredient list not extracted"

    ingredient_text = " | ".join(str(i).lower() for i in ingredients)

    found_banned = []
    for banned in banned_items:
        if banned in ingredient_text:
            found_banned.append(banned)

    if found_banned:
        return (
            CheckResult.FAIL,
            str(found_banned),
            f"BANNED ingredient(s) detected: {found_banned}"
        )
    return CheckResult.PASS, None, "No banned ingredients from this rule detected"


def _check_value_in_list(rule: ComplianceRule, config: dict, extraction: dict):
    field = config.get("field")
    allowed = [a.lower() for a in config.get("allowed_values", [])]

    if not field or not allowed:
        return CheckResult.SKIPPED, None, "Incomplete rule config"

    value = extraction.get(field)
    if not value:
        return CheckResult.FAIL, None, f"Field '{field}' is missing"

    if str(value).lower() in allowed:
        return CheckResult.PASS, str(value), f"'{field}' has an allowed value"
    return CheckResult.FAIL, str(value), f"'{field}' value not in allowed list: {allowed}"


def _check_format_llm(rule: ComplianceRule, config: dict, extraction: dict):
    """
    LLM-assisted format verification — uses Gemini to evaluate whether
    the extracted label data meets a format/layout requirement that can't
    be checked with simple regex (e.g. font size, prominence, bilingual text).

    Falls back to WARNING if Gemini is unavailable.
    """
    field = config.get("field")
    description = config.get("description", rule.description)

    # Gather relevant extracted data for context
    if field:
        value = extraction.get(field)
        if not value and value is not False:
            return CheckResult.FAIL, None, f"Required field '{field}' is missing — cannot verify format"
        context_data = f"Field '{field}' extracted value: {str(value)[:500]}"
    else:
        # No specific field — send broader extraction context
        relevant_keys = [k for k in extraction if extraction[k] and k != "_extraction_warnings"]
        context_data = "\n".join(f"  {k}: {str(extraction[k])[:200]}" for k in relevant_keys[:15])

    # ── Pull relevant regulation context from the KB (uploaded .md / PDF docs) ──
    kb_context = ""
    try:
        from app.database import SessionLocal as _SL
        from app.services.llm_service import retrieve_context as _rc
        _query = f"{rule.rule_code} {description[:200]}"
        _db = _SL()
        try:
            _chunks = _rc("regulations", _query, _db, top_k=4)
            if _chunks:
                kb_context = "\n\n".join(
                    f"[{c['document_title']}]\n{c['content']}" for c in _chunks
                )
        finally:
            _db.close()
    except Exception:
        pass

    kb_section = (
        f"\nKNOWLEDGE BASE (uploaded regulation documents):\n{kb_context}\n"
        if kb_context else ""
    )

    prompt = (
        "You are an FSSAI/Legal Metrology compliance auditor for Indian product labels.\n\n"
        f"RULE: {rule.rule_code} — {description}\n"
        f"REGULATION: {rule.regulation_source or 'N/A'}\n"
        f"{kb_section}"
        f"\nEXTRACTED LABEL DATA:\n{context_data}\n\n"
        "Based on the extracted data, can you determine if this format/layout requirement "
        "is likely met? Consider that you're working from extracted text — you cannot verify "
        "visual elements like font size or color, but you CAN verify:\n"
        "- Whether required text/declarations are present\n"
        "- Whether bilingual requirements are met (Hindi + English)\n"
        "- Whether numerical formats are correct\n"
        "- Whether required ordering/structure is followed\n\n"
        "Respond with ONLY valid JSON (no markdown):\n"
        '{"verdict": "PASS" or "FAIL" or "WARNING", '
        '"reason": "1-2 sentence explanation"}'
    )

    try:
        from app.config import get_settings
        settings = get_settings()
        import json

        raw = None

        # Gemini
        if raw is None and settings.gemini_api_key:
            try:
                from google import genai as _genai
                from google.genai import types as _genai_types
                _client = _genai.Client(api_key=settings.gemini_api_key)
                response = _client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt,
                    config=_genai_types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=256,
                    ),
                )
                raw = response.text.strip()
                try:
                    from app.services.api_logger import log_api_call
                    _usage = getattr(response, "usage_metadata", None)
                    _inp = getattr(_usage, "prompt_token_count", None) if _usage else None
                    _out = getattr(_usage, "candidates_token_count", None) if _usage else None
                    log_api_call("compliance_format", "gemini", "gemini-2.0-flash-lite", _inp, _out)
                except Exception:
                    pass
            except Exception as ge:
                logger.warning("[compliance] Gemini format check failed for %s: %s", rule.rule_code, ge)

        if raw is None:
            raise ValueError("No LLM provider available for format check")

        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result_json = json.loads(raw)

        verdict = result_json.get("verdict", "WARNING").upper()
        reason = result_json.get("reason", description)

        if verdict == "PASS":
            return CheckResult.PASS, str(value)[:200] if field else "verified", f"Format check passed: {reason}"
        elif verdict == "FAIL":
            return CheckResult.FAIL, str(value)[:200] if field else None, f"Format check failed: {reason}"
        else:
            return CheckResult.WARNING, str(value)[:200] if field else None, f"Format check inconclusive: {reason}"

    except ValueError:
        # No LLM provider configured at all — SKIP rather than inflate the score.
        # The product is not penalised; the admin dashboard will show this rule as
        # unverified so the user knows to do a manual check.
        logger.debug("[compliance] No LLM provider for FORMAT_LLM rule %s — skipping", rule.rule_code)
        return CheckResult.SKIPPED, None, "No LLM provider configured — manual verification required"
    except Exception as e:
        # Transient API error — flag as WARNING so the user knows the check is
        # unconfirmed but the score is not silently inflated to a full pass.
        logger.warning("[compliance] LLM format check failed for %s: %s", rule.rule_code, e)
        return CheckResult.WARNING, None, f"LLM check unavailable — manual verification required: {description}"


# ─── Deterministic FORMAT rule handlers ──────────────────────────────────────
# Each returns (CheckResult, actual_value_or_None, message_str).
# These run before any LLM call — they use only the extraction JSON.

def _handle_swtnr_001(extraction: dict):
    """Aspartame present → must carry phenylketonuric warning."""
    _ASPARTAME = {"aspartame", "ins 951", "ins951", "e951", "aspartame-acesulfame"}
    ing = _concat(extraction, "ingredient_list")
    if not any(a in ing for a in _ASPARTAME):
        return CheckResult.PASS, None, "No aspartame found in ingredients — warning not required"
    warn = _concat(extraction, "warnings", "health_claims")
    if "phenylketonuric" in warn:
        return CheckResult.PASS, "phenylketonuric warning found", "Aspartame warning 'Not recommended for phenylketonurics' is present"
    return CheckResult.FAIL, "phenylketonuric warning missing", (
        "Product contains aspartame but is missing 'Not recommended for phenylketonurics' warning"
    )


def _handle_swtnr_002(extraction: dict):
    """Non-caloric sweeteners → must declare 'CONTAINS NON-CALORIC SWEETENER'."""
    _SWEETENERS = {
        "stevia", "sucralose", "aspartame", "acesulfame", "saccharin",
        "neotame", "advantame", "monk fruit", "ins 950", "ins 951",
        "ins 952", "ins 954", "ins 955", "ins 960", "ins 961",
    }
    ing = _concat(extraction, "ingredient_list")
    if not any(s in ing for s in _SWEETENERS):
        return CheckResult.PASS, None, "No artificial/non-caloric sweeteners found — declaration not required"
    combined = _concat(extraction, "warnings", "health_claims", "product_name")
    if "non-caloric sweetener" in combined or "non caloric sweetener" in combined:
        return CheckResult.PASS, "declaration found", "'CONTAINS NON-CALORIC SWEETENER' declaration is present"
    return CheckResult.FAIL, None, (
        "Product contains artificial sweeteners but missing 'CONTAINS NON-CALORIC SWEETENER' declaration"
    )


def _handle_swtnr_003(extraction: dict):
    """Polyols → may need laxative effect warning (WARNING — can't confirm 10% threshold)."""
    _POLYOLS = {"sorbitol", "mannitol", "xylitol", "maltitol", "lactitol", "erythritol", "isomalt"}
    ing = _concat(extraction, "ingredient_list")
    found = [p for p in _POLYOLS if p in ing]
    if not found:
        return CheckResult.PASS, None, "No polyols found in ingredients — warning not required"
    warn = _concat(extraction, "warnings")
    if "laxative" in warn:
        return CheckResult.PASS, str(found), "Laxative effect warning is present for polyols"
    return CheckResult.WARNING, str(found), (
        f"Product contains polyols ({found}) — verify laxative effect warning is present if used at ≥10% by weight"
    )


def _handle_caff_001(extraction: dict):
    """Caffeine sources → must declare 'CONTAINS CAFFEINE'."""
    _CAFF = {"caffeine", "guarana", "green tea extract", "coffee extract", "kola nut", "yerba mate", "matcha"}
    ing = _concat(extraction, "ingredient_list")
    if not any(c in ing for c in _CAFF):
        return CheckResult.PASS, None, "No caffeine sources found in ingredients — declaration not required"
    combined = _concat(extraction, "warnings", "health_claims")
    if "contains caffeine" in combined:
        return CheckResult.PASS, "CONTAINS CAFFEINE found", "'CONTAINS CAFFEINE' declaration is present"
    return CheckResult.FAIL, None, (
        "Product contains caffeine sources but missing 'CONTAINS CAFFEINE' declaration"
    )


def _handle_glut_001(extraction: dict):
    """'Gluten Free' claim → must not contain wheat/barley/rye."""
    combined = _concat(extraction, "health_claims", "product_name", "warnings")
    if "gluten free" not in combined and "gluten-free" not in combined:
        return CheckResult.PASS, None, "No 'Gluten Free' claim found — declaration not required"
    ing = _concat(extraction, "ingredient_list")
    _GLUTEN = {"wheat", "barley", "rye", "oat"}
    found = [g for g in _GLUTEN if g in ing]
    if found:
        return CheckResult.FAIL, str(found), (
            f"'Gluten Free' claim is made but product appears to contain gluten sources: {found}"
        )
    return CheckResult.PASS, "Gluten Free claim valid", "Gluten Free claim present with no gluten-containing ingredients detected"


def _handle_alrg_001(extraction: dict):
    """Allergens in ingredients → should have allergen_declarations box."""
    allergens = extraction.get("allergen_declarations") or []
    if allergens:
        return CheckResult.PASS, str(allergens), f"Allergen declaration present: {allergens}"
    ing = _concat(extraction, "ingredient_list")
    _COMMON = {"milk", "egg", "fish", "crustacean", "tree nut", "peanut", "wheat", "soybean", "sesame", "gluten"}
    found = [a for a in _COMMON if a in ing]
    if found:
        return CheckResult.WARNING, str(found), (
            f"Possible allergens ({found}) found in ingredients but no allergen declaration detected — "
            "verify 'Contains: [allergen]' box is present separately from ingredients list"
        )
    return CheckResult.PASS, None, "No common allergens detected — allergen declaration not required"


def _handle_clm_brnd_001(extraction: dict):
    """Brand adjectives (Natural/Pure/Fresh/etc.) → require trademark disclaimer."""
    _ADJ = {"natural", "fresh", "pure", "original", "traditional", "authentic", "genuine", "real"}
    brand = _concat(extraction, "product_name")
    found = [a for a in _ADJ if re.search(r"\b" + a + r"\b", brand)]
    if not found:
        return CheckResult.PASS, None, "Product name/brand does not use regulated adjectives — disclaimer not required"
    warn = _concat(extraction, "warnings", "health_claims")
    if "brand name" in warn and "trademark" in warn:
        return CheckResult.PASS, str(found), "Brand trademark disclaimer is present"
    return CheckResult.WARNING, str(found), (
        f"Brand name contains regulated adjective(s) {found} — "
        "verify '*This is only a brand name or trademark, not representative of its true nature' disclaimer is present"
    )


def _handle_clm_med_001(extraction: dict):
    """No medical/healthcare professional endorsement claims."""
    combined = _concat(extraction, "health_claims", "warnings")
    _PROHIBITED = [
        "recommended by doctor", "recommended by physician", "recommended by nutritionist",
        "recommended by dietician", "doctor approved", "doctor-approved",
        "clinically recommended", "prescribed by", "endorsed by healthcare",
        "as recommended by your doctor", "doctor recommended", "physician recommended",
    ]
    found = [p for p in _PROHIBITED if p in combined]
    if found:
        return CheckResult.FAIL, str(found[:2]), f"Prohibited medical endorsement claim detected: {found[:2]}"
    return CheckResult.PASS, None, "No prohibited medical professional endorsement claims detected"


def _handle_clm_comp_001(extraction: dict):
    """No claims that disparage or undermine competitors."""
    combined = _concat(extraction, "health_claims", "warnings")
    _COMP = [
        "unlike other brands", "unlike conventional", "unlike other supplements",
        "better than", "other brands use fillers", "other brands use synthetics",
        "competitors use", "inferior brands", "unlike regular brands",
    ]
    found = [p for p in _COMP if p in combined]
    if found:
        return CheckResult.FAIL, str(found[:2]), f"Prohibited comparative/disparaging claim detected: {found[:2]}"
    return CheckResult.PASS, None, "No prohibited comparative claims detected"


def _handle_spt_lbl_001(extraction: dict):
    """Sports products → mandatory 'FOR SPORTSPERSON ONLY' declaration."""
    combined = _concat(extraction, "warnings", "health_claims", "product_type_declaration")
    if "sportsperson" in combined or "for sportsperson" in combined:
        return CheckResult.PASS, "FOR SPORTSPERSON ONLY found", "'FOR SPORTSPERSON ONLY' declaration is present"
    return CheckResult.FAIL, None, "Sports nutrition product missing mandatory 'FOR SPORTSPERSON ONLY' declaration"


def _handle_spt_warn_001(extraction: dict):
    """Sports products → must not contain WADA-prohibited substances."""
    _WADA = [
        "ephedrine", "sibutramine", "dmaa", "methylhexamine",
        "androstene", "prohormone", "clenbuterol",
        "ligandrol", "ostarine", "rad-140", "mk-677", "gw501516",
        "erythropoietin", "human growth hormone",
    ]
    ing = _concat(extraction, "ingredient_list", "health_claims")
    found = [s for s in _WADA if s in ing]
    if found:
        return CheckResult.FAIL, str(found[:3]), f"Potential WADA-prohibited substance detected: {found[:3]}"
    return CheckResult.PASS, None, "No WADA-prohibited substances detected in ingredient list or claims"


def _handle_fsmp_lbl_001(extraction: dict):
    """FSMP → must carry 'RECOMMENDED TO BE USED UNDER MEDICAL ADVICE ONLY'."""
    combined = _concat(extraction, "warnings", "health_claims")
    if "under medical advice" in combined or "medical advice only" in combined:
        return CheckResult.PASS, "medical advice statement found", "'RECOMMENDED TO BE USED UNDER MEDICAL ADVICE ONLY' is present"
    return CheckResult.FAIL, None, (
        "FSMP product missing mandatory 'RECOMMENDED TO BE USED UNDER MEDICAL ADVICE ONLY' statement in bold"
    )


def _handle_fsmp_lbl_002(extraction: dict):
    """FSMP → must carry 'For the dietary management of [condition]'."""
    combined = _concat(extraction, "warnings", "health_claims")
    if "dietary management of" in combined:
        return CheckResult.PASS, "dietary management statement found", "'For the dietary management of [condition]' statement is present"
    return CheckResult.FAIL, None, "FSMP product missing 'For the dietary management of [specific condition]' statement"


def _handle_fsmp_lbl_003(extraction: dict):
    """FSMP → must carry 'NOT FOR PARENTERAL USE'."""
    warn = _concat(extraction, "warnings")
    if "parenteral" in warn:
        return CheckResult.PASS, "NOT FOR PARENTERAL USE found", "'NOT FOR PARENTERAL USE' warning is present"
    return CheckResult.FAIL, None, "FSMP product missing 'NOT FOR PARENTERAL USE' warning"


def _handle_bot_lbl_001(extraction: dict):
    """Botanical/herbal ingredients → must include scientific (Latin) name."""
    ingredients = extraction.get("ingredient_list") or []
    if not ingredients:
        return CheckResult.PASS, None, "No ingredients found — botanical name check not applicable"
    _HERBS = {
        "ashwagandha", "turmeric", "bacopa", "moringa", "amla", "ginger",
        "tulsi", "brahmi", "shatavari", "neem", "guggul", "boswellia",
        "gokshura", "triphala", "shilajit", "arjuna", "guduchi", "punarnava",
        "haritaki", "amalaki", "bibhitaki",
    }
    ing_text = _norm(" ".join(str(i) for i in ingredients))
    found_herbs = [h for h in _HERBS if h in ing_text]
    if not found_herbs:
        return CheckResult.PASS, None, "No common herbal/botanical ingredients detected"
    # Latin binomial pattern: (Capitalized genus lowercase species)
    sci_pattern = r"\([A-Z][a-z]+ [a-z]+\)"
    raw_ing = " ".join(str(i) for i in ingredients)
    if re.search(sci_pattern, raw_ing):
        return CheckResult.PASS, str(found_herbs[:3]), "Botanical scientific names (Latin binomials) found in ingredients list"
    return CheckResult.WARNING, str(found_herbs[:3]), (
        f"Herbal ingredients detected ({found_herbs[:3]}) — verify each herb includes its scientific name, "
        "e.g. 'Ashwagandha (Withania somnifera)'"
    )


def _handle_bot_lbl_002(extraction: dict):
    """Botanical extracts → must declare extract ratio or standardisation %."""
    ingredients = extraction.get("ingredient_list") or []
    if not ingredients:
        return CheckResult.PASS, None, "No ingredients found — extract ratio check not applicable"
    raw_ing = _norm(" ".join(str(i) for i in ingredients))
    if "extract" not in raw_ing:
        return CheckResult.PASS, None, "No botanical extracts found in ingredients"
    _RATIO = re.compile(r"\d+:\d+|standardized? to \d+|std\.? to \d+|standardised? to \d+")
    if _RATIO.search(raw_ing):
        return CheckResult.PASS, "extract ratio declared", "Extract ratio or standardisation percentage is declared in ingredients"
    return CheckResult.WARNING, "extract(s) without ratio", (
        "Botanical extract(s) detected but extract ratio/standardisation may not be declared — "
        "e.g. add '10:1' or 'standardized to 5% withanolides'"
    )


def _handle_bot_warn_001(extraction: dict):
    """Schedule-IV contraindication herbs → must warn about pregnancy/disease."""
    _CONTRA_HERBS = {
        "andrographis", "berberine", "ephedra", "fenugreek", "ginseng",
        "licorice", "senna", "valerian", "vitex", "chastetree",
        "coleus forskohlii", "fennel seed", "panax ginseng",
    }
    ing = _concat(extraction, "ingredient_list")
    found = [h for h in _CONTRA_HERBS if h in ing]
    if not found:
        return CheckResult.PASS, None, "No Schedule IV contraindication herbs detected"
    warn = _concat(extraction, "warnings")
    if "pregnancy" in warn or "pregnant" in warn:
        return CheckResult.PASS, str(found), f"Pregnancy contraindication warning is present for herbs: {found}"
    return CheckResult.WARNING, str(found), (
        f"Herbs with potential pregnancy contraindications ({found}) detected — "
        "verify 'Not recommended during pregnancy' warning is present per FSSAI Schedule IV"
    )


def _handle_frt_warn_001(extraction: dict):
    """Iron-fortified products → must carry thalassemia/sickle cell advisory."""
    health = _concat(extraction, "health_claims", "warnings")
    ing = _concat(extraction, "ingredient_list")
    _FORT_IRON = {"fortified with iron", "iron fortified", "iron-fortified", "iron enriched", "iron-enriched"}
    is_iron_fortified = any(f in health for f in _FORT_IRON) or (
        any(x in ing for x in ("ferrous", "ferric")) and
        any(x in health for x in ("fortified", "enriched"))
    )
    if not is_iron_fortified:
        return CheckResult.PASS, None, "Product does not appear to be iron-fortified"
    if "thalassemia" in health or "sickle cell" in health:
        return CheckResult.PASS, "thalassemia advisory found", "Mandatory iron fortification advisory for thalassemia/sickle cell is present"
    return CheckResult.FAIL, None, (
        "Iron-fortified product missing mandatory advisory: "
        "'People with thalassemia may take under medical supervision and persons with Sickle Cell Anaemia are advised not to consume'"
    )


def _handle_vgn_lbl_001(extraction: dict):
    """Vegan claim → must display FSSAI vegan logo (veg_nonveg_mark = VEGAN)."""
    combined = _concat(extraction, "health_claims", "product_name", "warnings")
    if "vegan" not in combined and "plant-based" not in combined:
        return CheckResult.PASS, None, "No vegan claim detected — vegan logo not required"
    veg_mark = (extraction.get("veg_nonveg_mark") or "").upper().strip()
    if veg_mark == "VEGAN":
        return CheckResult.PASS, "VEGAN mark present", "Vegan claim made and FSSAI 'VEGAN' mark is confirmed on label"
    return CheckResult.WARNING, f"veg_nonveg_mark={veg_mark!r}", (
        "Vegan/plant-based claim detected but FSSAI 'VEGAN' mark could not be confirmed — "
        "verify the prescribed vegan logo is displayed on label"
    )


def _handle_prob_lbl_001(extraction: dict):
    """Probiotic products → must declare genus/species and CFU count."""
    _PROB_KEYWORDS = {
        "lactobacillus", "bifidobacterium", "saccharomyces", "streptococcus thermophilus",
        "live culture", "probiotic",
    }
    ing = _concat(extraction, "ingredient_list")
    health = _concat(extraction, "health_claims")
    found = [p for p in _PROB_KEYWORDS if p in ing or p in health]
    if not found:
        return CheckResult.PASS, None, "No probiotic organisms or claims detected"
    combined = ing + " " + health
    if re.search(r"cfu|colony forming unit", combined):
        return CheckResult.PASS, str(found[:2]), "Probiotic CFU (colony forming units) count is declared"
    return CheckResult.FAIL, str(found[:2]), (
        f"Probiotic product ({found[:2]}) missing mandatory CFU (colony forming units) count per serving"
    )


# FSSAI-NUTRA-NOVL-001 — Novel Food prior FSSAI approval
def _handle_nutra_novl_001(extraction: dict):
    ptd = _norm(extraction.get("product_type_declaration") or "")
    if "novel food" not in ptd:
        return CheckResult.PASS, None, "Product is not declared as Novel Food — prior approval check not applicable"
    # Novel Food declared — look for an approval reference anywhere on the label
    all_text = _concat(extraction, "warnings", "product_type_declaration", "notes", "health_claims")
    approval_kws = ["approved", "fssai approval", "approval no", "approval ref", "fssai order", "novel food approval"]
    for kw in approval_kws:
        if kw in all_text:
            return CheckResult.PASS, ptd, "Novel Food — FSSAI approval reference detected on label"
    return CheckResult.FAIL, ptd, (
        "Product declared as NOVEL FOOD but no FSSAI approval reference found. "
        "Novel Food cannot be marketed without prior FSSAI approval (Reg 13)."
    )


# FSSAI-NUTRA-PREBIOTIC-001 — Prebiotic characterisation (source + effective dose)
_PREBIOTIC_KEYWORDS = [
    "inulin", "fos", "fructo-oligosaccharide", "fructooligosaccharide",
    "galacto-oligosaccharide", "galactooligosaccharide", "gos",
    "lactulose", "pectin", "resistant starch", "arabinogalactan",
    "oligosaccharide", "prebiotic",
]

def _handle_nutra_prebiotic_001(extraction: dict):
    ing = _concat(extraction, "ingredient_list")
    found_pre = [kw for kw in _PREBIOTIC_KEYWORDS if kw in ing]
    if not found_pre:
        return CheckResult.PASS, None, "No prebiotic ingredients detected"
    # Prebiotic found — check for any quantity/dose in the ingredient text
    dose_match = re.search(r"\d+\s*(?:mg|g\b|mcg|μg)", ing)
    if dose_match:
        return CheckResult.PASS, str(found_pre[:2]), (
            f"Prebiotic ingredient(s) {found_pre[:2]} present with dose declaration"
        )
    return CheckResult.WARNING, str(found_pre[:2]), (
        f"Prebiotic ingredient(s) {found_pre[:2]} present but minimum effective dose per serving "
        "not clearly declared. Characterise source and effective dose per serving."
    )


# FSSAI-NUTRA-PIF-001 — Product Information File for botanical products
_BOTANICAL_KEYWORDS = [
    "ashwagandha", "withania", "turmeric", "curcuma", "ginseng", "panax",
    "green tea", "camellia", "moringa", "shatavari", "asparagus racemosus",
    "brahmi", "bacopa", "tulsi", "ocimum", "neem", "azadirachta",
    "guduchi", "tinospora", "triphala", "amla", "amalaki", "haritaki",
    "ginger", "zingiber", "boswellia", "shallaki", "valerian", "garlic",
    "allium", "elderberry", "sambucus", "echinacea", "milk thistle",
    "silybum", "gymnema", "fenugreek", "trigonella", "bitter melon",
    "momordica", "holy basil", "botanical extract", "herbal extract",
    "plant extract", "standardized extract", "standardised extract",
]

def _handle_nutra_pif_001(extraction: dict):
    ing = _concat(extraction, "ingredient_list")
    found_bot = [kw for kw in _BOTANICAL_KEYWORDS if kw in ing]
    if not found_bot:
        return CheckResult.PASS, None, "No botanical ingredients detected — PIF requirement not applicable"
    # Botanical found — check for PIF reference in any field
    all_text = _concat(extraction, "warnings", "notes", "health_claims", "certifications")
    pif_kws = ["product information file", "pif available", "pif on request", "product dossier"]
    for kw in pif_kws:
        if kw in all_text:
            return CheckResult.PASS, str(found_bot[:2]), "Botanical ingredients found with PIF reference on label"
    return CheckResult.WARNING, str(found_bot[:2]), (
        f"Botanical ingredient(s) {found_bot[:2]} present but no Product Information File (PIF) reference found. "
        "Add 'Product Information File available with manufacturer' to the label or package insert."
    )


# FSSAI-FSMP-OSM-001 — FSMP osmolality / osmolarity declaration
def _handle_fsmp_osm_001(extraction: dict):
    all_text = _concat(extraction,
                       "nutrition_facts", "warnings", "notes",
                       "product_type_declaration", "health_claims")
    osm_kws = ["osmolality", "osmolarity", "mosm", "mosmol"]
    for kw in osm_kws:
        if kw in all_text:
            return CheckResult.PASS, kw, "Osmolality/osmolarity declaration found on label"
    return CheckResult.FAIL, None, (
        "FSMP product is missing osmolality (mOsm/kg) or osmolarity (mOsm/L) declaration. "
        "This is mandatory for FSMP products under FSS Regulations 2016."
    )


# ─── Registry: rule_code → deterministic handler ─────────────────────────────
# Rules NOT in this dict fall through to the LLM batch call.

_DETERMINISTIC_FORMAT_HANDLERS: dict[str, object] = {
    "FSSAI-LBL-SWTNR-001": _handle_swtnr_001,
    "FSSAI-LBL-SWTNR-002": _handle_swtnr_002,
    "FSSAI-LBL-SWTNR-003": _handle_swtnr_003,
    "FSSAI-LBL-CAFF-001":  _handle_caff_001,
    "FSSAI-LBL-GLUT-001":  _handle_glut_001,
    "FSSAI-LBL-ALRG-001":  _handle_alrg_001,
    "FSSAI-CLM-BRND-001":  _handle_clm_brnd_001,
    "FSSAI-CLM-MED-001":   _handle_clm_med_001,
    "FSSAI-CLM-COMP-001":  _handle_clm_comp_001,
    "FSSAI-SPT-LBL-001":   _handle_spt_lbl_001,
    "FSSAI-SPT-WARN-001":  _handle_spt_warn_001,
    "FSSAI-FSMP-LBL-001":  _handle_fsmp_lbl_001,
    "FSSAI-FSMP-LBL-002":  _handle_fsmp_lbl_002,
    "FSSAI-FSMP-LBL-003":  _handle_fsmp_lbl_003,
    "FSSAI-BOT-LBL-001":   _handle_bot_lbl_001,
    "FSSAI-BOT-LBL-002":   _handle_bot_lbl_002,
    "FSSAI-BOT-WARN-001":  _handle_bot_warn_001,
    "FSSAI-FRT-WARN-001":  _handle_frt_warn_001,
    "FSSAI-VGN-LBL-001":         _handle_vgn_lbl_001,
    "FSSAI-PROB-LBL-001":        _handle_prob_lbl_001,
    # New rules — deterministic handlers (no Gemini call needed)
    "FSSAI-NUTRA-NOVL-001":      _handle_nutra_novl_001,
    "FSSAI-NUTRA-PREBIOTIC-001": _handle_nutra_prebiotic_001,
    "FSSAI-NUTRA-PIF-001":       _handle_nutra_pif_001,
    "FSSAI-FSMP-OSM-001":        _handle_fsmp_osm_001,
}


def _check_format_rules_batch(format_rules, extraction: dict, label_version_id: int) -> list:
    """
    Run ALL FORMAT / FORMAT_LLM rules in a single Gemini call instead of one
    call per rule.  Reduces ~43 sequential API calls (≈172 s) to 1 call (≈5 s).

    Falls back gracefully: if the LLM is unavailable every rule becomes WARNING.
    """
    import json as _json

    if not format_rules:
        return []

    # ── Pre-check: rules whose required field is missing → immediate FAIL ─────
    prefail = []
    pending_rules = []
    for rule in format_rules:
        config = rule.check_config or {}
        field = config.get("field")
        if field and not extraction.get(field) and extraction.get(field) is not False:
            prefail.append(ComplianceCheck(
                label_version_id=label_version_id,
                rule_id=rule.id,
                result=CheckResult.FAIL,
                actual_value=None,
                message=f"Required field '{field}' is missing — cannot verify format",
                remediation=rule.remediation_template or "",
            ))
        else:
            pending_rules.append(rule)

    if not pending_rules:
        return prefail

    # ── Build batch prompt ────────────────────────────────────────────────────
    relevant_keys = [k for k in extraction if extraction[k] and k != "_extraction_warnings"]
    label_summary = "\n".join(
        f"  {k}: {str(extraction[k])[:300]}" for k in relevant_keys[:20]
    )

    items_desc = []
    for i, rule in enumerate(pending_rules):
        config = rule.check_config or {}
        field = config.get("field")
        desc  = config.get("description") or rule.description
        if field:
            val = extraction.get(field, "")
            items_desc.append(
                f'{i+1}. [{rule.rule_code}] {desc}\n   Field "{field}" value: {str(val)[:200]}'
            )
        else:
            items_desc.append(f'{i+1}. [{rule.rule_code}] {desc}')

    prompt = (
        "You are an FSSAI / Legal Metrology compliance auditor for Indian product labels.\n\n"
        "EXTRACTED LABEL DATA:\n" + label_summary + "\n\n"
        "Evaluate ALL of the following format/content requirements based on the extracted data.\n"
        "For each, return PASS, FAIL, or WARNING with a 1-sentence reason.\n\n"
        + "\n".join(items_desc) + "\n\n"
        "Respond ONLY with a valid JSON array (no markdown fences):\n"
        '[{"rule_code":"X","verdict":"PASS","reason":"..."},...]'
    )

    # ── Call Gemini once ──────────────────────────────────────────────────────
    results_map: dict[str, tuple[str, str]] = {}
    try:
        from app.config import get_settings
        settings = get_settings()
        if not settings.gemini_api_key:
            raise ValueError("No Gemini key")

        from google import genai as _genai
        from google.genai import types as _genai_types
        _client = _genai.Client(api_key=settings.gemini_api_key)
        response = _client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=_genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        for item in _json.loads(raw):
            results_map[item["rule_code"]] = (
                item.get("verdict", "WARNING").upper(),
                item.get("reason", ""),
            )
        try:
            from app.services.api_logger import log_api_call
            _usage = getattr(response, "usage_metadata", None)
            _inp = getattr(_usage, "prompt_token_count", None) if _usage else None
            _out = getattr(_usage, "candidates_token_count", None) if _usage else None
            log_api_call("compliance_format_batch", "gemini", "gemini-2.0-flash-lite", _inp, _out)
        except Exception:
            pass
        logger.debug("[compliance] Batch FORMAT: %d rules → 1 Gemini call", len(pending_rules))
    except Exception as exc:
        logger.warning("[compliance] Batch FORMAT check failed: %s — falling back to WARNING", exc)

    # ── Convert verdicts → ComplianceCheck objects ────────────────────────────
    batch_checks = []
    for rule in pending_rules:
        config  = rule.check_config or {}
        field   = config.get("field")
        val     = extraction.get(field) if field else None
        verdict, reason = results_map.get(rule.rule_code, ("WARNING", "Batch format check unavailable"))

        if verdict == "PASS":
            result  = CheckResult.PASS
            msg     = f"Format check passed: {reason}"
            actual  = str(val)[:200] if field and val else "verified"
        elif verdict == "FAIL":
            result  = CheckResult.FAIL
            msg     = f"Format check failed: {reason}"
            actual  = str(val)[:200] if field and val else None
        else:
            result  = CheckResult.WARNING
            msg     = f"Format check inconclusive: {reason}"
            actual  = str(val)[:200] if field and val else None

        batch_checks.append(ComplianceCheck(
            label_version_id=label_version_id,
            rule_id=rule.id,
            result=result,
            actual_value=actual,
            message=msg,
            remediation=rule.remediation_template or "",
        ))

    return prefail + batch_checks


# ─── Compliance Score ─────────────────────────────────────────────────────────

# Deduction per failure — absolute penalty model so score doesn't depend on
# how many total rules apply.  2 CRITICAL failures → 100-20 = 80%.
_DEDUCTIONS = {
    Severity.CRITICAL: 10,
    Severity.HIGH:      6,
    Severity.MEDIUM:    3,
    Severity.LOW:       1,
}


def calculate_compliance_score(checks: list[ComplianceCheck]) -> int:
    """
    Penalty-based compliance score.

    Starts at 100 and deducts per violation:
      CRITICAL: -10   (2 criticals → 80%)
      HIGH:     -6
      MEDIUM:   -3
      LOW:      -1
      WARNING:  half the severity deduction (not a confirmed failure)

    Score is floored at 0. Independent of the total number of rules so
    adding more rules does not silently inflate scores.
    """
    if not checks:
        return 0

    deductions = 0.0
    for check in checks:
        if not check.rule:
            continue
        penalty = _DEDUCTIONS.get(check.rule.severity, 1)
        if check.result == CheckResult.FAIL:
            deductions += penalty
        elif check.result == CheckResult.WARNING:
            deductions += penalty * 0.5

    return max(0, round(100 - deductions))


def calculate_critical_score(checks: list[ComplianceCheck]) -> dict:
    """
    Returns critical-only compliance metrics.
    - critical_pass: True if ALL critical rules pass
    - critical_score: % of critical rules that pass
    - critical_failures: count of failed critical rules
    """
    critical_checks = [c for c in checks if c.rule and c.rule.severity == Severity.CRITICAL]
    if not critical_checks:
        return {"critical_pass": True, "critical_score": 100, "critical_failures": 0}

    failures = sum(1 for c in critical_checks if c.result == CheckResult.FAIL)
    passed = len(critical_checks) - failures
    return {
        "critical_pass": failures == 0,
        "critical_score": round((passed / len(critical_checks)) * 100),
        "critical_failures": failures,
    }


def get_violation_summary(checks: list[ComplianceCheck]) -> dict:
    """Returns a dict with counts by severity for failed checks."""
    from app.models import Severity
    summary = {s.value: 0 for s in Severity}
    for check in checks:
        if check.result == CheckResult.FAIL and check.rule:
            summary[check.rule.severity.value] += 1
    return summary
