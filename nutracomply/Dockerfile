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

# 4 workers: 2 handle live requests, 2 available for background scan tasks
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4"]
