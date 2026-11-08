# Single image used by BOTH the API and the worker Cloud Run services; they
# differ only by the container command. Migrations run as a separate Cloud Run
# Job from this same image (python -m scripts.migrate).
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching. Copy only the project
# metadata, install, then copy the source.
COPY pyproject.toml ./
# Create a throwaway package layout so pip can resolve the project before the
# real source is copied, then install dependencies only.
# (No RUN heredoc: Cloud Build's default legacy builder doesn't support it.)
RUN python -m pip install --upgrade pip \
    && python -c 'import tomllib, subprocess; deps = tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]; subprocess.check_call(["pip", "install", *deps])'

# Now copy the application source and install the package itself (no deps).
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN pip install --no-deps -e .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV APP_ENV=production \
    PORT=8080

EXPOSE 8080

# Default command: the API. Cloud Run sets $PORT (defaults to 8080 here). The
# worker service overrides this with:  python -m scripts.worker
# Using shell form so $PORT expands at runtime.
# --no-access-log: uvicorn access lines include the full query string, which on
# the webhook handshake contains hub.verify_token. Cloud Run's request log
# already records method/path/status/latency.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log
