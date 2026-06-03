# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy only manifest files — layer cached until pyproject.toml changes
COPY pyproject.toml README.md alembic.ini ./

# Install third-party deps only (no local project) — heavy downloads cached here
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project --extra docs --extra ocr --extra ml

# Copy source after deps — code changes only bust from this layer onward
COPY src/ src/
COPY alembic/ alembic/
COPY scripts/ scripts/

# Install local project (wheel build only, no downloads)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --extra docs --extra ocr --extra ml

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn invoice_pipeline.api.main:app --host 0.0.0.0 --port 8000"]
