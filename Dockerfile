FROM python:3.12-slim

WORKDIR /app

# System deps: OCR engines + PDF tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached unless requirements change)
COPY nutracomply/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY nutracomply/ .

EXPOSE 8000

# Railway injects $PORT; fall back to 8000 locally
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
