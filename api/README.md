# API

FastAPI service for the Consumer Product & Vehicle Safety Assistant.

## Endpoints

- `GET /api/health` — health check.
- `POST /api/chat` — answers recall questions. Body: `{"messages": [{"role": "user", "content": "..."}]}` (up to 20 messages, last must be from the user). Returns `{"answer": "...", "sources": [{"id", "agency", "title", "url"}]}`. Returns 503 when `OPENAI_API_KEY` is unset and 502 when the model call fails.

## Configuration

| Variable                                          | Default            | Purpose                          |
| ------------------------------------------------- | ------------------ | -------------------------------- |
| `OPENAI_API_KEY`                                  | unset              | Required for `/api/chat`         |
| `OPENAI_MODEL`                                    | `gpt-5.4-mini`     | OpenAI model used by the agent   |
| `NHTSA_API_URL` / `VPIC_API_URL` / `CPSC_API_URL` | official endpoints | Recall data sources              |
| `RECALL_API_TIMEOUT_SECONDS`                      | `15`               | Timeout for recall API requests  |
| `MAX_PRODUCT_RECALL_RESULTS`                      | `10`               | CPSC results passed to the model |

Tests use mocked HTTP transports and Pydantic AI `FunctionModel`, so they need no network access or API key.
