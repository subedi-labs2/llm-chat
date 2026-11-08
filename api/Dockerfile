FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# Keep the virtualenv outside /app so the dev source bind mount does not hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

FROM base AS dev

RUN uv sync --locked

COPY . .

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS builder

ENV UV_COMPILE_BYTECODE=1

RUN uv sync --locked --no-dev

FROM python:3.12-slim-bookworm AS prod

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

RUN useradd --system --uid 10001 --no-create-home app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src ./src

# Set by the Release workflow and reported by /api/health.
ARG APP_VERSION=dev
ARG APP_COMMIT=unknown
ENV APP_VERSION=$APP_VERSION \
    APP_COMMIT=$APP_COMMIT

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
