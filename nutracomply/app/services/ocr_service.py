"""
OCR Service — extracts raw text from label images and PDFs.

Priority:
1. PaddleOCR (images) — better accuracy for mixed English/Hindi labels
2. pdfplumber (PDFs) — direct text extraction from PDF
3. pytesseract fallback if PaddleOCR fails
"""

import io
from pathlib import Path
from typing import Optional


def extract_text_from_file(file_path: str) -> tuple[str, float]:
    """
    Returns (raw_text, confidence_score 0-1).
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_from_pdf(file_path)
    else:
        return _extract_from_image(file_path)


def _extract_from_pdf(file_path: str) -> tuple[str, float]:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        text = "\n".join(text_parts).strip()
        if text:
            return text, 0.95
    except Exception as e:
        print(f"[ocr] pdfplumber failed: {e}")

    # Fallback: convert PDF pages to images and OCR
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        all_text = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            page_text, _ = _ocr_image_bytes(img_bytes)
            all_text.append(page_text)
        return "\n".join(all_text).strip(), 0.80
    except Exception as e:
        print(f"[ocr] PDF→image fallback failed: {e}")
        return "", 0.0


def _extract_from_image(file_path: str) -> tuple[str, float]:
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    return _ocr_image_bytes(img_bytes)


def _ocr_image_bytes(img_bytes: bytes) -> tuple[str, float]:
    """Try PaddleOCR first, fall back to pytesseract."""
    # --- PaddleOCR ---
    try:
        from paddleocr import PaddleOCR
        import numpy as np
        import cv2

        # Preprocess: deskew + contrast
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        img = _preprocess_image(img)

        # Encode back to bytes for PaddleOCR
        _, buf = cv2.imencode(".png", img)

        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        result = ocr.ocr(buf.tobytes(), cls=True)

        lines = []
        confidences = []
        if result and result[0]:
            for line in result[0]:
                if line and len(line) >= 2:
                    text, conf = line[1][0], line[1][1]
                    lines.append(text)
                    confidences.append(conf)

        text = "\n".join(lines).strip()
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        if text:
            return text, round(avg_conf, 3)
    except Exception as e:
        print(f"[ocr] PaddleOCR failed: {e}")

    # --- pytesseract fallback ---
    try:
        import pytesseract
        from PIL import Image

        img_pil = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img_pil, lang="eng+hin")
        return text.strip(), 0.70
    except Exception as e:
        print(f"[ocr] pytesseract fallback failed: {e}")

    return "", 0.0


def _preprocess_image(img):
    """Deskew and enhance contrast for better OCR accuracy."""
    import cv2
    import numpy as np

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Enhance contrast using CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    # Convert back to BGR
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
