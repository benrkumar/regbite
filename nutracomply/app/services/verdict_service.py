"""
Shared compliance verdict helpers.
"""
from __future__ import annotations


def count_critical_failures(checks_or_results) -> int:
    total = 0
    for item in checks_or_results or []:
        result = getattr(item, "result", None)
        severity = None
        rule = getattr(item, "rule", None)
        if rule is not None:
            severity = getattr(rule, "severity", None)
        if isinstance(item, dict):
            result = item.get("result", result)
            severity = item.get("severity", severity)
        result_value = getattr(result, "value", result)
        severity_value = getattr(severity, "value", severity)
        if result_value == "FAIL" and severity_value == "CRITICAL":
            total += 1
    return total


def build_verdict(score: int | None, critical_failures: int) -> str:
    score = score or 0
    if critical_failures == 0 and score >= 90:
        return "COMPLIANT"
    if critical_failures == 0 and score >= 60:
        return "PARTIAL"
    return "NON_COMPLIANT"


def verdict_tone(verdict: str | None) -> str:
    if verdict == "COMPLIANT":
        return "good"
    if verdict == "PARTIAL":
        return "warn"
    return "bad"


def verdict_label(verdict: str | None) -> str:
    if verdict == "COMPLIANT":
        return "Compliant"
    if verdict == "PARTIAL":
        return "Partial"
    if verdict == "NON_COMPLIANT":
        return "Non-Compliant"
    return "Pending"


def summarize_checks(checks) -> dict:
    checks = list(checks or [])
    if not checks:
        return {
            "score": None,
            "critical_failures": 0,
            "verdict": None,
            "tone": "none",
            "label": "No label",
            "passed_count": 0,
            "failed_count": 0,
            "warning_count": 0,
            "total_checks": 0,
        }

    from app.services.compliance_engine import calculate_compliance_score

    passed_count = 0
    failed_count = 0
    warning_count = 0
    for check in checks:
        result_value = getattr(getattr(check, "result", None), "value", getattr(check, "result", None))
        if result_value == "PASS":
            passed_count += 1
        elif result_value == "FAIL":
            failed_count += 1
        elif result_value == "WARNING":
            warning_count += 1

    score = calculate_compliance_score(checks)
    critical_failures = count_critical_failures(checks)
    verdict = build_verdict(score, critical_failures)
    return {
        "score": score,
        "critical_failures": critical_failures,
        "verdict": verdict,
        "tone": verdict_tone(verdict),
        "label": verdict_label(verdict),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "warning_count": warning_count,
        "total_checks": len(checks),
    }
