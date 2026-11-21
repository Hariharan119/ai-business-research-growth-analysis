"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_log_level: str = "INFO"
    cors_allowed_origins: str = "http://localhost:5173"

    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'local_dev.db').as_posix()}"

    sec_user_agent: str = ""
    sec_base_url: str = "https://data.sec.gov"
    sec_requests_per_second: float = Field(default=5.0, gt=0, le=10)
    sec_cache_ttl_hours: float = 12.0

    newsdata_api_key: str = ""
    newsdata_base_url: str = "https://newsdata.io/api/1"
    newsdata_language: str = "en"
    newsdata_page_size: int = Field(default=10, ge=1, le=50)
    newsdata_max_pages: int = Field(default=3, ge=1, le=10)
    newsdata_min_interval_seconds: float = 2.0
    newsdata_cache_ttl_minutes: float = 60.0

    llm_provider: str = "groq"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_timeout_seconds: float = 90.0
    llm_max_attempts: int = Field(default=3, ge=1, le=6)

    http_timeout_seconds: float = 30.0
    http_max_attempts: int = Field(default=3, ge=1, le=10)
    cache_dir: Path = REPO_ROOT / "data" / "cache"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def require_sec_user_agent(self) -> str:
        """Return the SEC User-Agent value or raise when it is missing or a placeholder."""
        value = self.sec_user_agent.strip()
        if not value or "@" not in value or value.lower().startswith("replace_with"):
            raise ConfigurationError("SEC_USER_AGENT must contain a name and a contact email address.")
        return value

    def require_newsdata_key(self) -> str:
        value = self.newsdata_api_key.strip()
        if not value or value.lower().startswith("replace_with"):
            raise ConfigurationError("NEWSDATA_API_KEY is not configured.")
        return value

    def require_llm_key(self) -> str:
        value = self.llm_api_key.strip()
        if not value or value.lower().startswith("replace_with"):
            raise ConfigurationError("LLM_API_KEY is not configured.")
        return value

    def require_llm_model(self) -> str:
        value = self.llm_model.strip()
        if not value or value.lower().startswith("replace_with"):
            raise ConfigurationError("LLM_MODEL is not configured.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
