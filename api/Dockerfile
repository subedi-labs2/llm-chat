FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Keep the virtualenv outside /app so the source bind mount does not hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked

COPY . .

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
