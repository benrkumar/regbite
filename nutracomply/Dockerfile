FROM python:3.12-slim

WORKDIR /app

# System deps: Tesseract (OCR fallback) + poppler (PDF utils)
# Note: libglib/libsm/opencv removed — PaddleOCR no longer used
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 1 worker: required for in-memory _SCAN_JOBS dict to be shared across all requests.
# With multiple workers, status polls can hit a different process that has no job state.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
