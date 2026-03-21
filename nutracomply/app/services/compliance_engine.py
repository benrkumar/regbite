"""
Compliance Engine — runs all active rules against an extracted label JSON.
Covers FSSAI, Legal Metrology, and AYUSH (ASU) regulations.
Returns a list of ComplianceCheck results with PASS/FAIL/WARNING + remediation.
"""

import re
from typing import Optional
from sqlalchemy.orm import Session

from app.models import ComplianceRule, ComplianceCheck, LabelVersion, CheckType, CheckResult, Severity


def run_compliance_check(label_version: LabelVersion, db: Session) -> list[ComplianceCheck]:
    """
    Runs all active rules against the label_version's extraction_json.
    Saves and returns ComplianceCheck records.
    """
    extraction = label_version.extraction_json or {}
    rules = db.query(ComplianceRule).filter(ComplianceRule.active == True).all()

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
            # Format checks are advisory — mark as WARNING if we can't verify automatically
            result = CheckResult.WARNING
            message = f"Manual verification required: {config.get('description', rule.description)}"

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

    value = extraction.get(field)

    # Boolean fields (e.g. not_for_medicinal_use)
    if isinstance(value, bool):
        if value:
            return CheckResult.PASS, "true", f"'{field}' is confirmed present on label"
        else:
            return CheckResult.FAIL, "false", f"Required statement not found on label"

    # Required text pattern within a list of strings
    required_text = config.get("required_text")
    if required_text and isinstance(value, list):
        combined = " ".join(str(v).lower() for v in value)
        if required_text.lower() in combined:
            return CheckResult.PASS, required_text, f"Required text '{required_text}' found"
        else:
            return CheckResult.FAIL, None, f"Required text '{required_text}' not found in {field}"

    # Allowed values
    allowed_values = config.get("allowed_values")
    if allowed_values and isinstance(value, str):
        for av in allowed_values:
            if av.lower() in value.lower():
                return CheckResult.PASS, value, f"Valid product type declaration found: '{value}'"
        return CheckResult.FAIL, value, f"Product type declaration must be one of: {allowed_values}"

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


# ─── Compliance Score ─────────────────────────────────────────────────────────

def calculate_compliance_score(checks: list[ComplianceCheck]) -> int:
    if not checks:
        return 0
    total = len(checks)
    passed = sum(1 for c in checks if c.result == CheckResult.PASS)
    return round((passed / total) * 100)


def get_violation_summary(checks: list[ComplianceCheck]) -> dict:
    """Returns a dict with counts by severity for failed checks."""
    from app.models import Severity
    summary = {s.value: 0 for s in Severity}
    for check in checks:
        if check.result == CheckResult.FAIL and check.rule:
            summary[check.rule.severity.value] += 1
    return summary
