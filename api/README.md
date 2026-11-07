# API

FastAPI service for the Consumer Product & Vehicle Safety Assistant.

## Endpoints

- `GET /api/health` — health check.
- `GET /api/chat/config` — returns `{"default_backend": "pydantic_ai" | "langchain", "backend_selection": bool}` so the web app knows whether to show the agent framework toggle.
- `POST /api/chat` — answers recall questions. Body: `{"messages": [{"role": "user", "content": "..."}], "backend": "langchain"}` (up to 20 messages, last must be from the user; `backend` is optional and only honored when `ALLOW_BACKEND_SELECTION` is on). Returns `{"answer": "...", "sources": [{"id", "agency", "title", "url"}], "backend": "..."}`, where `backend` is the agent that answered. Returns 503 when `GEMINI_API_KEY` is unset and 502 when the model call fails.

## Configuration

| Variable                                          | Default                                         | Purpose                                                                                  |
| ------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `AGENT_BACKEND`                                   | `pydantic_ai`                                   | Agent framework: `pydantic_ai` or `langchain` (see below)                                |
| `ALLOW_BACKEND_SELECTION`                         | `false`                                         | Let requests pick the agent backend; the web app then shows a toggle                     |
| `GEMINI_API_KEY`                                  | unset                                           | Required for `/api/chat`                                                                 |
| `GEMINI_MODEL`                                    | `gemini-3.8-flash`                              | Gemini model used by the agent                                                           |
| `GEMINI_FALLBACK_MODELS`                          | `["gemini-3.6-flash", "gemini-3.5-flash-lite"]` | JSON list tried in order when the primary model is overloaded or failing (`[]` disables) |
| `GEMINI_RETRY_ATTEMPTS`                           | `2`                                             | Attempts per model for transient errors (429, 5xx)                                       |
| `NHTSA_API_URL` / `VPIC_API_URL` / `CPSC_API_URL` | official endpoints                              | Recall data sources                                                                      |
| `RECALL_API_TIMEOUT_SECONDS`                      | `15`                                            | Timeout for recall API requests                                                          |
| `MAX_PRODUCT_RECALL_RESULTS`                      | `10`                                            | CPSC results passed to the model                                                         |

## Agent backends

The chat agent has two interchangeable implementations with the same instructions, tools, output schema, grounding check, model fallback, and usage limits:

- `pydantic_ai` (default): `src/chat/agent.py`, built on Pydantic AI.
- `langchain`: `src/chat/langchain_agent.py`, built on LangChain `create_agent` with `langchain-google-genai`. Fallback models, usage limits, tool retry feedback, and the grounding check are agent middleware.

Shared prompts, schemas, and grounding helpers live in `src/chat/agent.py`.

With `ALLOW_BACKEND_SELECTION=true` (set in `.env.example` for local development), the web app shows a Pydantic AI / LangChain toggle in the header, remembers the choice in the browser, and labels each answer with the backend that produced it. Keep it off for public deployments: the app has no login, so any visitor could switch backends.

Tests use mocked HTTP transports with Pydantic AI `FunctionModel` (`tests/test_chat.py`) or a scripted LangChain chat model (`tests/test_chat_langchain.py`), so they need no network access or API key.
