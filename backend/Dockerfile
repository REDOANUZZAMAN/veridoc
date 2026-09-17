# ============================================================================
# VeriDoc API / worker image
#
# One image serves both roles; the compose file overrides the command:
#   api     uvicorn app.main:app
#   worker  python -m app.workers.worker
#
# System packages are the real dependencies of the analysis pipeline:
#   tesseract-ocr    pixel OCR for scans and photographs
#   poppler-utils    PDF page rasterisation (pdftoppm)
#   libmagic1        content-type sniffing at ingest
#   libgl/libglib    OpenCV runtime for the forensic metrics
# ============================================================================
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
        libmagic1 \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so application edits do not invalidate the wheel layer.
# PIP_INDEX_URL lets a build behind a slow link point at a mirror without
# changing the file:  docker compose build --build-arg PIP_INDEX_URL=...
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org
COPY requirements.txt ./
RUN pip install --index-url "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" \
        -r requirements.txt

COPY . .

# Run unprivileged; the storage volume is the only writable path required.
RUN useradd --create-home --uid 10001 veridoc \
    && mkdir -p /var/veridoc/storage \
    && chown -R veridoc:veridoc /var/veridoc /app
USER veridoc

ENV STORAGE_LOCAL_ROOT=/var/veridoc/storage

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
