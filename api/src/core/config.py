from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AgentBackend = Literal["pydantic_ai", "langchain"]


class Settings(BaseSettings):
    app_name: str = "Consumer Product & Vehicle Safety API"
    app_env: Literal["development", "test", "production"] = "development"
    # Release version and git commit of this build, set by the image build.
    app_version: str = "dev"
    app_commit: str = "unknown"

    # Framework that runs the chat agent. Both use the same Gemini settings below.
    agent_backend: AgentBackend = "pydantic_ai"
    # Let chat requests choose the agent backend (shown as a toggle in the web app).
    allow_backend_selection: bool = False
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    # Tried in order when the primary model is overloaded, rate limited, or failing.
    gemini_fallback_models: list[str] = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]
    gemini_retry_attempts: int = 2

    nhtsa_api_url: str = "https://api.nhtsa.gov"
    vpic_api_url: str = "https://vpic.nhtsa.dot.gov/api"
    cpsc_api_url: str = "https://www.saferproducts.gov/RestWebServices"
    recall_api_timeout_seconds: float = 15.0
    max_product_recall_results: int = 10

    # Voice input: base URL of a speaches server (e.g. http://stt:8000). Unset disables it.
    stt_url: str | None = None
    stt_model: str = "Systran/faster-distil-whisper-small.en"
    # Spoken language hint; None lets the model detect it.
    stt_language: str | None = "en"
    # Concurrent voice sessions per API replica; each one keeps a CPU core busy on the STT server.
    stt_max_sessions: int = 2
    stt_max_session_seconds: float = 120.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
