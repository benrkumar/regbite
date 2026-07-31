# Root Dockerfile — builds the FastAPI compliance app in nutracomply/.
#
# Railway's "steadfast-courage" service (project blissful-simplicity, serving
# www.regbite.com) builds from the REPOSITORY ROOT, so this file has to live
# here and reference nutracomply/ explicitly. It was deleted by the monorepo
# restructure in 8720ac4, which silently broke every deploy from that point on
# — the app stayed frozen on the last good image while pushes appeared to
# succeed. Do not remove it without also changing the service's build settings.
#
# nutracomply/Dockerfile is the equivalent for building from inside that
# directory; keep the two in sync.

FROM python:3.12-slim

WORKDIR /app

# System deps: Tesseract (OCR fallback) + poppler (PDF utils) + libgomp1.
# libglib/libsm/libxext/libxrender are intentionally absent — they were only
# needed by PaddleOCR, which is no longer used. libgomp1 stays: scikit-learn
# needs the OpenMP runtime, and app/services/pattern_library.py imports it
# inside a try/except, so a missing libgomp1 would not crash the app — it would
# silently disable the pattern library instead. That is far worse than a 2 MB
# package.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    poppler-utils libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first so this layer caches unless they change
COPY nutracomply/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY nutracomply/ .

EXPOSE 8000

# 1 worker: required for the in-memory _SCAN_JOBS dict to be shared across all
# requests. With multiple workers, status polls can hit a different process
# that has no job state.
#
# --proxy-headers / --forwarded-allow-ips: Railway's edge proxy is the sole
# ingress and rewrites X-Forwarded-For, so trusting it is safe here. Without
# these, uvicorn's default forwarded_allow_ips="127.0.0.1" makes it IGNORE the
# proxy headers, which means:
#   - request.client.host is the proxy's IP, not the visitor's -> per-IP rate
#     limiting collapses into a single global bucket for the whole internet
#   - request.url.scheme is "http" -> secure= is False on every cookie we set
# Both matter for the anonymous upload path in app/routes/checker.py.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
