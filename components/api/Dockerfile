# Dashboard API image. It imports the SHARED SQLAlchemy models from
# components/whatsapp/api (package `app`) via the runtime bridge in
# dash/shared_db.py, so the image bundles BOTH trees.
#
# IMPORTANT: build this with the context at `components/` (the parent of api/),
# not at components/api/, so both source trees are available:
#
#   gcloud builds submit --tag "$IMAGE" -f api/Dockerfile components/
#   # or locally:  docker build -f api/Dockerfile -t dashboard-api components/
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Install dependencies first for layer caching (dashboard deps are a superset of
# what the bridge needs from whatsapp/api).
COPY api/pyproject.toml ./api/pyproject.toml
RUN python -m pip install --upgrade pip \
    && python -c 'import tomllib, subprocess; deps = tomllib.load(open("api/pyproject.toml", "rb"))["project"]["dependencies"]; subprocess.check_call(["pip", "install", *deps])'

# Bring in both source trees. The dashboard (`dash`) imports whatsapp/api's
# `app` package through the path the bridge resolves (../whatsapp/api).
COPY api/ ./api/
COPY whatsapp/api/ ./whatsapp/api/

WORKDIR /srv/api
RUN pip install --no-deps -e .

# Non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /srv
USER appuser

ENV APP_ENV=production \
    PORT=8080
EXPOSE 8080

# Cloud Run sets $PORT. --no-access-log keeps request URLs (which may carry
# tokens on other services) out of stdout; Cloud Run logs method/path/status.
CMD exec uvicorn dash.main:app --host 0.0.0.0 --port ${PORT} --no-access-log
