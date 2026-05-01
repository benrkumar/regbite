from __future__ import annotations

from collections import defaultdict
from typing import Any


IMPACT_LABELS = {
    1: "Minimal",
    2: "Minor",
    3: "Moderate",
    4: "Major",
    5: "Critical",
}

LIKELIHOOD_LABELS = {
    1: "Unknown",
    2: "Guarded",
    3: "Possible",
    4: "Likely",
    5: "Confirmed",
}

CELL_OFFSETS = [
    (0.0, 0.0),
    (-0.18, -0.16),
    (0.18, -0.14),
    (-0.16, 0.16),
    (0.16, 0.16),
    (0.0, -0.24),
    (0.0, 0.24),
]


def _short_code(name: str, index: int) -> str:
    parts = [part.strip() for part in (name or "").replace("/", " ").replace("-", " ").split() if part.strip()]
    if len(parts) >= 2:
        code = (parts[0][:1] + parts[1][:1]).upper()
    elif parts:
        code = parts[0][:2].upper()
    else:
        code = f"P{index}"
    return code[:3]


def _impact_bucket(card: dict[str, Any]) -> tuple[int, str]:
    label_state = card.get("label_state")
    summary = card.get("summary") or {}
    critical_failures = summary.get("critical_failures", 0) or 0
    failed_count = summary.get("failed_count", 0) or 0
    warning_count = summary.get("warning_count", 0) or 0
    score = summary.get("score")
    verdict = summary.get("verdict")

    if label_state == "missing":
        return 3, "No current label is attached, so portfolio risk is materially unknown."
    if label_state == "failed":
        return 4, "The latest scan failed, so this product is operating without a trusted compliance result."
    if label_state in {"queued", "processing"}:
        return 2, "A scan is in progress, so the current risk picture is still being assembled."

    score = score or 0
    if critical_failures >= 3 or failed_count >= 15 or score < 70:
        return 5, "Multiple critical or widespread failures create a severe regulatory exposure."
    if critical_failures >= 1 or failed_count >= 8 or score < 85:
        return 4, "The latest label contains major gaps that are likely to trigger remediation."
    if verdict == "PARTIAL" or failed_count >= 3 or warning_count >= 3:
        return 3, "The label needs meaningful corrective work before it can be treated as low risk."
    if warning_count > 0 or score < 95:
        return 2, "The label is broadly healthy but still carries some residual compliance drag."
    return 1, "The latest label looks stable with no meaningful control breakage."


def _likelihood_bucket(card: dict[str, Any]) -> tuple[int, str]:
    label = card.get("label")
    label_state = card.get("label_state")
    summary = card.get("summary") or {}
    critical_failures = summary.get("critical_failures", 0) or 0
    verdict = summary.get("verdict")
    needs_review = bool(card.get("needs_review"))
    extraction_confidence = getattr(label, "extraction_confidence", 0.0) or 0.0

    if label_state in {"queued", "processing"}:
        return 1, "Evidence is still incomplete because the scan is actively running."
    if label_state == "missing":
        return 2, "A label gap indicates a plausible blind spot, but not yet a confirmed failure."
    if label_state == "failed":
        return 2, "A failed scan creates uncertainty that should be treated as guarded risk."

    if critical_failures >= 2 and not needs_review:
        return 5, "The failures are strong enough that this looks like a confirmed compliance issue."
    if verdict == "NON_COMPLIANT" and not needs_review:
        return 4, "The evidence strongly suggests a real compliance problem."
    if needs_review and extraction_confidence < 0.8:
        return 2, "The signal is still guarded because extraction confidence is low."
    if needs_review:
        return 3, "There are material warning signs, but a human should confirm the extraction."
    if verdict == "PARTIAL":
        return 3, "The label likely needs changes, but the current issues are not fully escalated."
    return 1, "Current evidence suggests a low likelihood of near-term compliance disruption."


def _matrix_priority(item: dict[str, Any]) -> tuple[int, int, int]:
    return (
        item["risk_score"],
        item["critical_failures"],
        item["failed_count"],
    )


def build_product_risk_matrix(product_cards: list[dict[str, Any]]) -> dict[str, Any]:
    ready_scores = [card["summary"]["score"] for card in product_cards if card.get("summary", {}).get("score") is not None]
    avg_score = round(sum(ready_scores) / len(ready_scores), 1) if ready_scores else 0.0

    breakdown = {
        "healthy": 0,
        "watchlist": 0,
        "critical": 0,
        "blind_spots": 0,
    }

    cell_counts: dict[tuple[int, int], int] = defaultdict(int)
    items: list[dict[str, Any]] = []

    def _sort_card(card: dict[str, Any]) -> tuple[int, int, int]:
        summary = card.get("summary") or {}
        score = summary.get("score")
        return (
            summary.get("critical_failures", 0) or 0,
            summary.get("failed_count", 0) or 0,
            -score if score is not None else 1,
        )

    sorted_cards = sorted(
        product_cards,
        key=_sort_card,
        reverse=True,
    )

    for index, card in enumerate(sorted_cards, 1):
        product = card["product"]
        label = card.get("label")
        summary = card.get("summary") or {}
        impact, impact_note = _impact_bucket(card)
        likelihood, likelihood_note = _likelihood_bucket(card)
        verdict = summary.get("verdict") or "UNKNOWN"
        label_state = card.get("label_state") or "missing"
        critical_failures = summary.get("critical_failures", 0) or 0
        failed_count = summary.get("failed_count", 0) or 0
        warning_count = summary.get("warning_count", 0) or 0
        risk_score = impact * likelihood

        if label_state in {"missing", "failed"}:
            breakdown["blind_spots"] += 1
        elif verdict == "COMPLIANT" and not card.get("needs_review"):
            breakdown["healthy"] += 1
        elif verdict == "PARTIAL" or card.get("needs_review"):
            breakdown["watchlist"] += 1
        else:
            breakdown["critical"] += 1

        cell_key = (impact, likelihood)
        offset_index = cell_counts[cell_key]
        cell_counts[cell_key] += 1
        offset_x, offset_y = CELL_OFFSETS[offset_index % len(CELL_OFFSETS)]

        size = 38 + max(0, impact - 3) * 4
        left_pct = ((impact - 0.5 + offset_x) / 5) * 100
        top_pct = (1 - ((likelihood - 0.5 + offset_y) / 5)) * 100

        score = summary.get("score")
        score_text = f"{score}%" if score is not None else "No score"
        focus_note = (
            f"{summary.get('label') or 'No label'} - {score_text} - "
            f"{critical_failures} critical - {failed_count} failing checks"
        )
        item = {
            "product_id": product.id,
            "product_name": product.name,
            "short_code": _short_code(product.name, index),
            "impact": impact,
            "impact_label": IMPACT_LABELS[impact],
            "likelihood": likelihood,
            "likelihood_label": LIKELIHOOD_LABELS[likelihood],
            "score": score,
            "score_text": score_text,
            "verdict": verdict,
            "verdict_label": summary.get("label") or "No label",
            "tone": card.get("tone") or "none",
            "label_state": label_state,
            "label_state_label": (
                "Review needed" if card.get("needs_review")
                else label_state.replace("_", " ").title()
            ),
            "needs_review": bool(card.get("needs_review")),
            "critical_failures": critical_failures,
            "failed_count": failed_count,
            "warning_count": warning_count,
            "risk_score": risk_score,
            "focus_note": focus_note,
            "impact_note": impact_note,
            "likelihood_note": likelihood_note,
            "focus_reason": f"{impact_note} {likelihood_note}",
            "left_pct": max(8, min(92, round(left_pct, 2))),
            "top_pct": max(8, min(92, round(top_pct, 2))),
            "size_px": size,
            "detail_href": f"/labels/{label.id}" if label else f"/products/{product.id}",
            "product_href": f"/products/{product.id}",
            "file_name": getattr(label, "file_name", "") if label else "",
        }
        items.append(item)

    items.sort(key=_matrix_priority, reverse=True)
    focus = items[0] if items else None
    hotspot_count = sum(1 for item in items if item["risk_score"] >= 16)
    watch_count = sum(1 for item in items if 9 <= item["risk_score"] < 16)

    return {
        "x_labels": ["Minimal", "Minor", "Moderate", "Major", "Critical"],
        "y_labels": ["Unknown", "Guarded", "Possible", "Likely", "Confirmed"],
        "items": items,
        "focus": focus,
        "average_score": avg_score,
        "ready_products": len(ready_scores),
        "hotspot_count": hotspot_count,
        "watch_count": watch_count,
        "breakdown": breakdown,
    }
