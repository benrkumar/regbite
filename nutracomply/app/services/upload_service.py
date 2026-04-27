from __future__ import annotations

import uuid
from pathlib import Path


ALLOWED_LABEL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".pdf", ".webp"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

MAGIC_SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"%PDF": ".pdf",
    b"II\x2a\x00": ".tiff",
    b"MM\x00\x2a": ".tiff",
}


def _matches_webp(content: bytes) -> bool:
    return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"


def detect_upload_extension(content: bytes) -> str | None:
    for signature, ext in MAGIC_SIGNATURES.items():
        if content[:len(signature)] == signature:
            return ext
    if _matches_webp(content):
        return ".webp"
    return None


def validate_upload_content(
    filename: str,
    content: bytes,
    allowed_extensions: set[str] | None = None,
) -> str:
    allowed = allowed_extensions or ALLOWED_LABEL_EXTENSIONS
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(allowed))}"
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("File too large. Maximum size is 50 MB.")

    detected_ext = detect_upload_extension(content)
    if not detected_ext:
        raise ValueError("File content does not match a supported image or PDF format.")

    normalized_suffix = ".tiff" if suffix in {".tif", ".tiff"} else ".jpg" if suffix in {".jpg", ".jpeg"} else suffix
    if normalized_suffix != detected_ext:
        raise ValueError(
            f"File content does not match the uploaded extension ('{suffix}')."
        )

    return detected_ext


def persist_upload_bytes(root_dir: str, namespace: str, suffix: str, content: bytes) -> Path:
    upload_dir = Path(root_dir) / namespace
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}{suffix}"
    file_path = upload_dir / file_name
    file_path.write_bytes(content)
    return file_path

