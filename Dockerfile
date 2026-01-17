# =============================================================================
# Backend Dockerfile for Legal Lease RAG API
# =============================================================================
# This is a multi-stage build to keep the final image small:
#   Stage 1: Build dependencies (installs everything)
#   Stage 2: Runtime (copies only what's needed to run)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install all dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies needed for building Python packages
# - gcc, python3-dev: Required for compiling some Python packages (numpy, etc.)
# - libffi-dev: Required for cryptography/security packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment (keeps dependencies isolated)
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first (Docker layer caching optimization)
# This layer is cached unless requirements.txt changes
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.11-slim as runtime

WORKDIR /app

# Install LibreOffice and Microsoft-compatible fonts for better DOCX conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-liberation \
    fonts-dejavu-core \
    fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with home directory for LibreOffice
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home appuser && \
    mkdir -p /home/appuser/.cache/dconf && \
    chown -R appuser:appuser /home/appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/appuser

COPY --chown=appuser:appuser . .

RUN mkdir -p data data/temp input output processed .flashrank_cache && \
    chown -R appuser:appuser data input output processed .flashrank_cache

USER appuser

# Expose the API port
EXPOSE 8000

# Health check - Docker will restart container if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Start with Gunicorn + Uvicorn workers (production ASGI server)
# - 1 worker: Single file watcher and pending queue (avoids duplicates)
# - UvicornWorker: Async support for FastAPI
# - 300s timeout: Long timeout for LLM operations (parsing, generation)
CMD ["gunicorn", "src.api.server:app", \
    "--workers", "1", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "150", \
    "--access-logfile", "-", \
    "--error-logfile", "-"]
