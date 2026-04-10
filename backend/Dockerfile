# ---- Build Stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.11-slim AS runtime

# Create non-root user for security
RUN groupadd -r famos && useradd -r -g famos -d /app -s /sbin/nologin famos

WORKDIR /app

# Copy installed packages from builder (smaller final image)
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create required directories and set permissions
RUN mkdir -p /app/instance /app/secure_uploads /app/logs \
    && chown -R famos:famos /app

# Switch to non-root user
USER famos

# Expose the app port
EXPOSE 5000

# Health check — Docker will restart the container if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Use gunicorn for production
CMD ["gunicorn", \
     "--workers", "3", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--access-logfile", "/app/logs/access.log", \
     "--error-logfile", "/app/logs/error.log", \
     "--log-level", "info", \
     "run:app"]
