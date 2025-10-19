# Dockerfile for Analyzer Service (Celery + Polars)
# Optimized for ARM64 (Raspberry Pi)

FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/analyzer/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared models from parent project
COPY shared/models/ ./shared/models/

# Copy application code
COPY services/analyzer/src/ ./src/
COPY services/analyzer/tests/ ./tests/

# Add src to PYTHONPATH
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import sys; from celery_app import app; sys.exit(0 if app else 1)"

# Default command (will be overridden by K8s)
CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info"]
