# Consumer Product & Vehicle Safety Assistant

An early foundation for a public-facing assistant that will help people research product and vehicle safety. This repository currently provides a FastAPI health API and a responsive React application shell; recall data and AI features are intentionally out of scope.

## Structure

- `api/` — FastAPI service managed with uv
- `web/` — React, TypeScript, Vite, Tailwind CSS, and shadcn/ui
- `.github/workflows/` — pull request and `main` branch checks

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 24+
- npm 11+

## Local development

Install dependencies:

```bash
cd api && uv sync --locked
cd ../web && npm ci
```

Start the API and web app in separate terminals:

```bash
cd api && uv run uvicorn src.main:app --reload
cd web && npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` requests to the API at `http://localhost:8000` by default. Copy `api/.env.example` to `api/.env` or `web/.env.example` to `web/.env` only when overriding their defaults.

## Quality checks

```bash
cd api
uv run ruff check .
uv run ruff format --check .
uv run pytest

cd ../web
npm run lint
npm run format:check
npm run typecheck
npm run build
```

Use `uv run ruff format .` and `npm run format` to format code. GitHub Actions runs the same checks for pull requests and pushes to `main`.
