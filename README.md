# Consumer Product & Vehicle Safety Assistant

A public-facing assistant that helps people research product and vehicle safety. A FastAPI service answers recall questions with a Google Gemini model (via [Pydantic AI](https://ai.pydantic.dev/)) that calls live NHTSA and CPSC recall APIs as tools, and a React app provides the chat interface.

## How answers stay grounded

- The model is instructed to state recall facts only from tool results, never from memory, and to ask for missing details (make, model, year, or VIN) instead of guessing.
- Tools: `decode_vin` (NHTSA vPIC), `search_vehicle_recalls` (NHTSA recalls by make/model/year), and `search_product_recalls` (CPSC, newest first, capped at `MAX_PRODUCT_RECALL_RESULTS`).
- If a source is unreachable, the tool tells the model so it can say it couldn't check instead of inventing an answer.
- Answers may only cite or mention recalls retrieved by a tool during the request. An output check also scans the answer text for NHTSA campaign numbers. If anything else appears, the model is told which IDs are unsupported and must correct the answer; if it can't, the API returns 502 instead of publishing unsupported claims.

## Structure

- `api/` — FastAPI service managed with uv (`src/recalls` data clients, `src/chat` agent and `/api/chat` endpoint)
- `web/` — React, TypeScript, Vite, Tailwind CSS, and shadcn/ui
- `.github/workflows/` — pull request and `main` branch checks

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 24+
- npm 11+

## Local development

### With Docker Compose

Start the API and web app together:

```bash
docker compose up --build
```

Open <http://localhost:5173>; the API is also available at <http://localhost:8000>. Source folders are mounted into the containers, so code changes reload automatically. To enable chat, set `GEMINI_API_KEY` in `api/.env` (copy `api/.env.example`) and run `docker compose restart api`. After changing dependencies, rebuild with `docker compose up --build --renew-anon-volumes`. Stop everything with `docker compose down`.

### Without Docker

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

Set `GEMINI_API_KEY` in `api/.env` (copy `api/.env.example`) to enable chat. You can create a free key in [Google AI Studio](https://aistudio.google.com/apikey); without it `/api/chat` returns 503. Open <http://localhost:5173>. Vite proxies `/api` requests to the API at `http://localhost:8000` by default. Copy `api/.env.example` to `api/.env` or `web/.env.example` to `web/.env` only when overriding their defaults.

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

## Container images

Every push to `main` publishes production images to GitHub Container Registry for whichever of `api/` or `web/` changed (run the **Release Images** workflow manually to publish both):

- `ghcr.io/subedi-labs2/safety-assistant-backend` — FastAPI on port 8000; configure it with the same environment variables as `api/.env.example`.
- `ghcr.io/subedi-labs2/safety-assistant-frontend` — the built web app served by nginx on port 8080, which proxies `/api` to `API_UPSTREAM` (default `http://backend:8000`).

Each image is tagged `latest` and `sha-<short commit>`. Both Dockerfiles are multistage: Compose uses the `dev` stage, and releases use `prod`. To build a production image locally, run `docker build --target prod api` or `docker build --target prod web`.
