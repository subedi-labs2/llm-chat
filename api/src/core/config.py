from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Consumer Product & Vehicle Safety API"
    app_env: Literal["development", "test", "production"] = "development"

    # Framework that runs the chat agent. Both use the same Gemini settings below.
    agent_backend: Literal["pydantic_ai", "langchain"] = "pydantic_ai"
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
