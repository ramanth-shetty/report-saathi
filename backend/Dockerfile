# ==============================================================================
# ReportSaathi Backend Service (FastAPI + Tesseract OCR + Google GenAI)
# Multi-stage build targeting Debian Bookworm Slim for glibc wheel compatibility
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build virtualenv with compiled dependencies
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for compiling Python packages with C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create isolated virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Minimal runtime image with Tesseract OCR & Indic language packs
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime OS packages:
# - tesseract-ocr, tesseract-ocr-hin (Hindi), tesseract-ocr-kan (Kannada)
# - libgl1 and libglib2.0-0 for OpenCV headless decoding
# - curl for Docker HEALTHCHECK probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-kan \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Security: Create and run as unprivileged non-root user (UID 10001)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -M appuser

# Copy application code and shared contract domain
COPY --chown=appuser:appgroup backend/ ./backend/
COPY --chown=appuser:appgroup shared/ ./shared/

USER appuser

EXPOSE 8000

# Health check probing zero-dependency GET /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Execute uvicorn with dynamic PORT binding
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
