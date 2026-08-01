# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy only manifest files — layer cached until pyproject.toml/uv.lock changes
COPY pyproject.toml uv.lock README.md alembic.ini ./

# Install third-party deps only (no local project) — heavy downloads cached here
# --frozen: use the committed lockfile exactly, never silently re-resolve
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra docs --extra ocr --extra ml

# Copy source after deps — code changes only bust from this layer onward
COPY src/ src/
COPY alembic/ alembic/
COPY scripts/ scripts/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Install local project (wheel build only, no downloads)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra docs --extra ocr --extra ml

RUN groupadd --system appuser && useradd --system --gid appuser --home-dir /app --no-create-home appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser:appuser /app

# appuser has no home dir — point HOME at /app (already owned by appuser) so
# uv/other tools can create their runtime cache dirs instead of failing on
# a missing/unwritable /home/appuser.
ENV HOME=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/health', timeout=3)" || exit 1

# Stay root until entrypoint chowns the (possibly stale-permissioned) mounted
# upload volume, then gosu drops to appuser before exec'ing the real command.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn invoice_pipeline.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
