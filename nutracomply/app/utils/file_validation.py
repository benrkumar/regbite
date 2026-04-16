"""
Shared file-upload validation utilities.

Centralises magic-byte checking so that every upload entry point
(label upload, quick checker, bulk upload) applies the same rules.
"""

# Maps leading byte sequences to canonical file extension
MAGIC_SIGNATURES = {
    b"\xff\xd8\xff":      ".jpg",   # JPEG
    b"\x89PNG\r\n\x1a\n": ".png",   # PNG
    b"%PDF":              ".pdf",   # PDF
    b"II\x2a\x00":        ".tiff",  # TIFF little-endian
    b"MM\x00\x2a":        ".tiff",  # TIFF big-endian
    b"RIFF":              ".webp",  # WebP (RIFF container)
}

ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif", ".pdf", ".webp"})


def validate_file_magic(content: bytes) -> str | None:
    """Return the detected file extension ('.jpg', '.png', '.pdf', …) or
    ``None`` if the content does not match any known signature.

    Usage::

        ext = validate_file_magic(file_bytes)
        if ext is None:
            # reject the upload
    """
    for sig, ext in MAGIC_SIGNATURES.items():
        if content[: len(sig)] == sig:
            return ext
    return None
