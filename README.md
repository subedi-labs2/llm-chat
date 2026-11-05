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
- `charts/` — Helm charts for the API and web, released independently
- `infra/` — local k3d cluster config, per-environment chart values, and the Cloudflare Tunnel connector
- `.github/workflows/` — pull request and `main` branch checks, image and chart releases

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

- `ghcr.io/subedi-labs2/llm-chat-api` — FastAPI on port 8000; configure it with the same environment variables as `api/.env.example`.
- `ghcr.io/subedi-labs2/llm-chat-web` — the built web app served by nginx on port 8080, which proxies `/api` to `API_UPSTREAM` (default `http://backend:8000`). The API address is looked up per request, so web starts before the API exists. In Kubernetes, set `API_UPSTREAM` to the Service's fully qualified name, such as `http://api.<namespace>.svc.cluster.local:8000`.

Each image is tagged `latest` and `sha-<full commit SHA>`. Both Dockerfiles are multistage: Compose uses the `dev` stage, and releases use `prod`. To build a production image locally, run `docker build --target prod api` or `docker build --target prod web`.

## Kubernetes (Helm)

The API and web have separate Helm charts, published to GHCR as OCI artifacts:

- `oci://ghcr.io/subedi-labs2/charts/llm-chat-api` — Service named after the release (install as `api`).
- `oci://ghcr.io/subedi-labs2/charts/llm-chat-web` — proxies `/api` to `http://api.<release namespace>.svc.cluster.local:8000` by default; override with `apiUpstream`.

Install the API and web in either order. Web returns 502 for `/api` until the API is ready.

### Local cluster (k3d, e.g. on WSL2)

Requires Docker, [k3d](https://k3d.io), kubectl, and Helm.

```bash
k3d cluster create --config infra/k3d.yaml

kubectl create namespace llm-chat
read -rsp "Gemini API key: " key && echo
kubectl -n llm-chat create secret generic llm-chat-api --from-literal=GEMINI_API_KEY="$key"

helm upgrade --install api oci://ghcr.io/subedi-labs2/charts/llm-chat-api \
  -n llm-chat -f infra/environments/wsl/api-values.yaml --wait
helm upgrade --install web oci://ghcr.io/subedi-labs2/charts/llm-chat-web \
  -n llm-chat -f infra/environments/wsl/web-values.yaml --wait
```

Open http://localhost:8080. Add `--version <x.y.z>` to pin a chart version. To test unpublished changes, use `charts/api` or `charts/web` instead of the `oci://` reference.

### Public access (Cloudflare Tunnel)

Expose the local cluster on a public domain (for example `llmchat.pukarsubedi.com`) without port forwarding. The domain's DNS must be managed by Cloudflare.

1. In the Cloudflare Zero Trust dashboard, open **Networks → Tunnels → Create a tunnel**, choose **Cloudflared**, and name it. Copy the token: the `eyJ…` string after `--token` in the shown command. Do not run the command itself.
2. Run the connector in the cluster:

   ```bash
   read -rsp "Tunnel token (eyJ...): " token && echo
   kubectl -n llm-chat create secret generic cloudflared --from-literal=token="$token"
   kubectl apply -n llm-chat -f infra/environments/wsl/cloudflared.yaml
   kubectl -n llm-chat rollout status deploy/cloudflared
   ```

3. Back in the dashboard, click **Continue** once the connector shows as connected, then add a published application (route):
   - **Subdomain / Domain:** `llmchat` / `pukarsubedi.com`
   - **Service URL:** `http://traefik.kube-system.svc.cluster.local:80` (not `localhost`, which is the cloudflared pod itself)
   - Leave the other settings at their defaults.
4. Open https://llmchat.pukarsubedi.com.

The site is only up while the machine and cluster are running. The app has no login, so consider protecting the hostname with **Zero Trust → Access → Applications** to keep others from using your Gemini quota.

Troubleshooting: `kubectl -n llm-chat logs -l app=cloudflared`. `Provided Tunnel token is not valid` means the secret holds more than the `eyJ…` token; recreate it with `kubectl -n llm-chat delete secret cloudflared` and repeat step 2.

### Releases

1. A push to `main` that changes `api/` or `web/` publishes a new image. The **Release Images** workflow then opens a PR that pins that image's digest in the chart and bumps the chart's patch version.
2. CI lints and validates the charts, requires a version bump for any chart change, and installs both charts into a kind cluster.
3. Merging a chart change runs **Release Charts**, which publishes any chart version not already in GHCR.

The chart PR is opened by a GitHub App so CI runs on it. One-time setup:

1. Create a GitHub App owned by the organization, with webhooks disabled and repository permissions **Contents: Read and write** and **Pull requests: Read and write**. Install it on this repository only.
2. In this repository's **Settings → Secrets and variables → Actions**, add the variable `RELEASE_BOT_CLIENT_ID` (the App's client ID) and the secret `RELEASE_BOT_PRIVATE_KEY` (a private key generated for the App).

