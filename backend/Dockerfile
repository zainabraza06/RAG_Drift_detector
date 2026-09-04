# Backend image: FastAPI + Chroma + SQLite.
#
# Built from the repository root, not from backend/, because the demo corpus
# and golden set live at ../demo and are baked in so the container is
# explorable with no external setup.
#
#   docker build -f backend/Dockerfile -t drift-backend .

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is only here for the container healthcheck; nothing in the application
# shells out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies are copied and installed on their own layer so a source change
# does not invalidate the (slow) dependency install.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# app/core/config.py resolves BACKEND_DIR to /app and REPO_ROOT to /, so the
# default demo_dir of <repo>/demo lands exactly here without configuration.
COPY demo/ /demo/

# Run unprivileged. The data directory is the only writable path the
# application needs, and it is where the compose volume mounts.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data
USER appuser

ENV DRIFT_DATA_DIR=/app/data \
    DRIFT_ENVIRONMENT=production \
    DRIFT_LOG_LEVEL=INFO

EXPOSE 8000

# The API's own health endpoint returns 503 when the database or the vector
# store is unreachable, so this reports genuine readiness rather than merely
# that a process is listening.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:8000/api/health || exit 1

# Migrations and the demo bootstrap run inside the application lifespan, so
# there is no separate init step to forget.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
