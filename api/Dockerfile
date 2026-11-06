# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# WeasyPrint (PDF export) needs Pango/Cairo; libpq for asyncpg is statically linked.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 libgdk-pixbuf-2.0-0 \
    shared-mime-info fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /bin/
WORKDIR /app

FROM base AS deps
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM base AS runtime
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/uploads && chown -R app:app /data
COPY --from=deps /app/.venv /app/.venv
COPY --chown=app:app . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["jobhunt", "api"]
