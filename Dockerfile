# ── Stage 1: builder ─────────────────────────────────────────────────────────
# Install dependencies in a separate stage so the final image stays small.
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps required to compile psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create non-root user — never run production apps as root
RUN useradd -m -u 1000 njangui && chown -R njangui:njangui /app
USER njangui

# Expose the port FastAPI runs on
EXPOSE 8000

# Startup: run migrations first, then start the server.
# PORT env var is set by Railway/Render automatically.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
