from __future__ import annotations


def estimate_scan_minutes(file_types: list[str] | None = None, *, default_count: int = 1) -> tuple[int, int]:
    types = list(file_types or [])
    if not types:
        types = ["image"] * max(default_count, 1)

    base_minutes = 0.0
    for file_type in types:
        normalized = (file_type or "image").lower()
        if normalized == "pdf":
            base_minutes += 2.8
        else:
            base_minutes += 1.8

    low = max(1, int(round(base_minutes * 0.85)))
    high = max(low + 1, int(round(base_minutes * 1.35)))
    return low, high


def format_eta_window(file_types: list[str] | None = None, *, default_count: int = 1) -> str:
    low, high = estimate_scan_minutes(file_types, default_count=default_count)
    if low == high:
        return f"about {low} min"
    return f"about {low}-{high} min"
