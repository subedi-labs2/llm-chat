# API

FastAPI service for the Consumer Product & Vehicle Safety Assistant.

## Endpoints

- `GET /api/health` — health check.
- `POST /api/chat` — answers recall questions. Body: `{"messages": [{"role": "user", "content": "..."}]}` (up to 20 messages, last must be from the user). Returns `{"answer": "...", "sources": [{"id", "agency", "title", "url"}]}`. Returns 503 when `GEMINI_API_KEY` is unset and 502 when the model call fails.

## Configuration

| Variable                                          | Default                                         | Purpose                                                                                  |
| ------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`                                  | unset                                           | Required for `/api/chat`                                                                 |
| `GEMINI_MODEL`                                    | `gemini-3.8-flash`                              | Gemini model used by the agent                                                           |
| `GEMINI_FALLBACK_MODELS`                          | `["gemini-3.6-flash", "gemini-3.5-flash-lite"]` | JSON list tried in order when the primary model is overloaded or failing (`[]` disables) |
| `GEMINI_RETRY_ATTEMPTS`                           | `2`                                             | Attempts per model for transient errors (429, 5xx)                                       |
| `NHTSA_API_URL` / `VPIC_API_URL` / `CPSC_API_URL` | official endpoints                              | Recall data sources                                                                      |
| `RECALL_API_TIMEOUT_SECONDS`                      | `15`                                            | Timeout for recall API requests                                                          |
| `MAX_PRODUCT_RECALL_RESULTS`                      | `10`                                            | CPSC results passed to the model                                                         |

Tests use mocked HTTP transports and Pydantic AI `FunctionModel`, so they need no network access or API key.
