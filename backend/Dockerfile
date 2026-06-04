FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/README.md ./README.md
RUN pip install --no-cache-dir -e .

# Copy source
COPY backend/src/ ./src/
COPY backend/config/ ./config/
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Non-root user
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/.runtime \
    && chown -R appuser:appuser /app \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]