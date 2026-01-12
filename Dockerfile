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

# Set working directory
WORKDIR /app

# Create non-root user for security (never run containers as root in production)
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash appuser

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set Python environment variables
# PYTHONUNBUFFERED: Ensures real-time log output (critical for Docker logs)
# PYTHONDONTWRITEBYTECODE: Prevents .pyc file clutter in container
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories with proper permissions
# These will be mounted as volumes in docker-compose
RUN mkdir -p data input output processed .flashrank_cache && \
    chown -R appuser:appuser data input output processed .flashrank_cache

# Switch to non-root user
USER appuser

# Expose the API port
EXPOSE 8000

# Health check - Docker will restart container if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Start with Gunicorn + Uvicorn workers (production ASGI server)
# - 4 workers: Good for handling concurrent requests
# - UvicornWorker: Async support for FastAPI
# - 120s timeout: Long timeout for LLM operations (parsing, generation)
CMD ["gunicorn", "src.api.server:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
