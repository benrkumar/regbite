"""
Compliance Engine — runs all active rules against an extracted label JSON.
Covers FSSAI, Legal Metrology, and AYUSH (ASU) regulations.
Returns a list of ComplianceCheck results with PASS/FAIL/WARNING + remediation.

v2 improvements:
  - Severity-weighted compliance scoring (CRITICAL=4x, HIGH=3x, MEDIUM=2x, LOW=1x)
  - LLM-assisted FORMAT checks (verifies format via Gemini instead of blanket WARNING)
  - Smarter field normalization before comparisons
"""

import re
from typing import Optional
from sqlalchemy.orm import Session

from app.models import ComplianceRule, ComplianceCheck, LabelVersion, CheckType, CheckResult, Severity

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
    all_rules = db.query(ComplianceRule).filter(ComplianceRule.active == True).all()

    # Filter rules by product category and framework
    product_category = (label_version.product.category or "").lower().strip()
    is_ayurvedic = "ayurvedic" in product_category or "asu" in product_category
    is_imported = bool(
        extraction.get("country_of_origin")
        and "india" not in str(extraction.get("country_of_origin", "")).lower()
    )

    rules = []
    for rule in all_rules:
        code = rule.rule_code or ""
        # AYUSH rules only apply to Ayurvedic/ASU products
        if code.startswith("AYUSH-") and not is_ayurvedic:
            continue
        # DGFT import rules only apply to imported products
        if code.startswith("DGFT-") and not is_imported:
            continue
        # Licensing rules are FORMAT checks — always include for awareness
        # BIS rules always apply (voluntary but checked)
        rules.append(rule)

    # Delete previous checks for this label version
    db.query(ComplianceCheck).filter(
        ComplianceCheck.label_version_id == label_version.id
    ).delete()

    checks = []
    for rule in rules:
        check = _evaluate_rule(rule, extraction, label_version.id)
        db.add(check)
        checks.append(check)

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

        elif rule.check_type == CheckType.FORMAT:
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
            return CheckResult.FAIL, "false", f"Required statement not found on label"

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
    return CheckResult.PASS, None, f"No banned ingredients from this rule detected"


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

    try:
        from app.config import get_settings
        settings = get_settings()
        if not settings.gemini_api_key:
            raise ValueError("No API key")

        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = (
            "You are an FSSAI/Legal Metrology compliance auditor for Indian product labels.\n\n"
            f"RULE: {rule.rule_code} — {description}\n"
            f"REGULATION: {rule.regulation_source or 'N/A'}\n\n"
            f"EXTRACTED LABEL DATA:\n{context_data}\n\n"
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

        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 256},
        )

        import json
        raw = response.text.strip()
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

    except Exception as e:
        print(f"[compliance] LLM format check failed for {rule.rule_code}: {e}")
        # Graceful fallback to WARNING
        return CheckResult.WARNING, None, f"Manual verification required: {description}"


# ─── Compliance Score ─────────────────────────────────────────────────────────

def calculate_compliance_score(checks: list[ComplianceCheck]) -> int:
    """
    Severity-weighted compliance score.
    CRITICAL rules count 4x, HIGH 3x, MEDIUM 2x, LOW 1x.
    This means failing a CRITICAL rule drops the score much more than failing a LOW rule.
    """
    if not checks:
        return 0

    weighted_earned = 0
    weighted_total = 0

    for check in checks:
        weight = SEVERITY_WEIGHTS.get(check.rule.severity, 1) if check.rule else 1
        weighted_total += weight
        if check.result == CheckResult.PASS:
            weighted_earned += weight
        elif check.result == CheckResult.WARNING:
            # Warnings get half credit — not a failure, but not confirmed
            weighted_earned += weight * 0.5

    if weighted_total == 0:
        return 0
    return round((weighted_earned / weighted_total) * 100)


def get_violation_summary(checks: list[ComplianceCheck]) -> dict:
    """Returns a dict with counts by severity for failed checks."""
    from app.models import Severity
    summary = {s.value: 0 for s in Severity}
    for check in checks:
        if check.result == CheckResult.FAIL and check.rule:
            summary[check.rule.severity.value] += 1
    return summary
