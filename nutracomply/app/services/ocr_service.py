"""
OCR Service — extracts raw text from label images and PDFs.

This is the FALLBACK path only. Claude Vision is the primary extraction method
and reads images directly without needing OCR.

Priority:
1. pdfplumber (PDFs) — fast direct text extraction from digital PDFs
2. PyMuPDF + pytesseract (image-only PDFs) — convert pages then OCR
3. pytesseract (images) — lightweight fallback, no model loading overhead

Note: PaddleOCR removed. It loaded 3 neural-network models per call (~15–25s
startup) which blocked the pipeline even when Claude Vision was used. Claude
Vision reads the image directly and never needed OCR text.
"""

import io
from pathlib import Path


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
    # pdfplumber — instant for digital PDFs (most regulation/supplement label PDFs)
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

    # Fallback: convert PDF pages to images and run pytesseract
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        all_text = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            page_text, _ = _ocr_image_bytes(img_bytes)
            if page_text:
                all_text.append(page_text)
        doc.close()
        return "\n".join(all_text).strip(), 0.75
    except Exception as e:
        print(f"[ocr] PDF→image fallback failed: {e}")
        return "", 0.0


def _extract_from_image(file_path: str) -> tuple[str, float]:
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    return _ocr_image_bytes(img_bytes)


def _ocr_image_bytes(img_bytes: bytes) -> tuple[str, float]:
    """pytesseract OCR — lightweight fallback when Claude Vision is unavailable.

    No model initialization overhead (unlike PaddleOCR which took 15-25s to load).
    Supports Hindi + English labels via 'eng+hin' language pack.
    """
    try:
        import pytesseract
        from PIL import Image
        img_pil = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img_pil, lang="eng+hin")
        return text.strip(), 0.70
    except Exception as e:
        print(f"[ocr] pytesseract failed: {e}")

    return "", 0.0
