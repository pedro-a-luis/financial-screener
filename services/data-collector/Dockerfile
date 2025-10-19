# Dockerfile for Data Collector Service
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

# Copy requirements first (for Docker layer caching)
COPY services/data-collector/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared models
COPY shared/models/ ./shared/models/

# Copy application code
COPY services/data-collector/src/ ./src/

# Copy ticker lists
COPY config/tickers/ ./config/tickers/

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src:/app

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import sys; sys.exit(0)"

# Default command (can be overridden by CronJob)
CMD ["python", "src/main.py", "--help"]
