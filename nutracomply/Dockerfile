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
#
# --proxy-headers / --forwarded-allow-ips: Railway's edge proxy is the sole ingress and
# rewrites X-Forwarded-For, so trusting it is safe here. Without these, uvicorn's default
# forwarded_allow_ips="127.0.0.1" makes it IGNORE the proxy headers, which means:
#   - request.client.host is the proxy's IP, not the visitor's  -> per-IP rate limiting
#     collapses into a single global bucket for the whole internet
#   - request.url.scheme is "http" -> secure=  is False on every cookie we set
# Both matter for the anonymous upload path in app/routes/checker.py.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
