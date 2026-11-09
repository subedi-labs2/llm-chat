# API

FastAPI service for the Consumer Product & Vehicle Safety Assistant.

## Endpoints

- `GET /api/health` — health check.
- `GET /api/chat/config` — returns `{"default_backend": "pydantic_ai" | "langchain", "backend_selection": bool, "voice_input": bool}` so the web app knows whether to show the agent framework toggle and the microphone button.
- `POST /api/chat` — answers recall questions. Body: `{"messages": [{"role": "user", "content": "..."}], "backend": "langchain"}` (up to 20 messages, last must be from the user; `backend` is optional and only honored when `ALLOW_BACKEND_SELECTION` is on). Returns `{"answer": "...", "sources": [{"id", "agency", "title", "url"}], "backend": "..."}`, where `backend` is the agent that answered. Returns 503 when `GEMINI_API_KEY` is unset and 502 when the model call fails.
- `WS /api/transcribe` — voice input, relayed to a [speaches](https://speaches.ai) realtime endpoint at `STT_URL`. The client sends binary frames of 16-bit little-endian, 24 kHz mono PCM (at most 48,000 bytes each), then `{"type": "stop"}` when the user stops. The server sends `{"type": "ready"}`, `{"type": "speech_started"}`, and `{"type": "transcript", "text": "..."}` once per phrase, and closes with code 1000 after the last transcript. Error close codes: 4400 invalid audio, 4408 session time limit, 4429 too many sessions, 4502 speech-to-text failed or unreachable, 4503 not configured.

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
| `STT_URL`                                         | unset                                           | speaches base URL (for example `http://stt:8000`); unset disables voice input            |
| `STT_MODEL`                                       | `Systran/faster-distil-whisper-small.en`        | Transcription model; must be downloaded on the speaches server                           |
| `STT_LANGUAGE`                                    | `en`                                            | Spoken language passed to the model                                                      |
| `STT_MAX_SESSIONS`                                | `2`                                             | Concurrent voice sessions per API process; more are rejected with 4429                   |
| `STT_MAX_SESSION_SECONDS`                         | `120`                                           | Longest voice session before it is closed with 4408                                      |

## Agent backends

The chat agent has two interchangeable implementations with the same instructions, tools, output schema, grounding check, model fallback, and usage limits:

- `pydantic_ai` (default): `src/chat/agent.py`, built on Pydantic AI.
- `langchain`: `src/chat/langchain_agent.py`, built on LangChain `create_agent` with `langchain-google-genai`. Fallback models, usage limits, tool retry feedback, and the grounding check are agent middleware.

Shared prompts, schemas, and grounding helpers live in `src/chat/agent.py`.

With `ALLOW_BACKEND_SELECTION=true` (set in `.env.example` for local development), the web app shows a Pydantic AI / LangChain toggle in the header, remembers the choice in the browser, and labels each answer with the backend that produced it. Keep it off for public deployments: the app has no login, so any visitor could switch backends.

Tests use mocked HTTP transports with Pydantic AI `FunctionModel` (`tests/test_chat.py`) or a scripted LangChain chat model (`tests/test_chat_langchain.py`), so they need no network access or API key. `tests/test_transcribe.py` relays audio through a fake speaches WebSocket server.
