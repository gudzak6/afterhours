"""Runtime configuration. Secrets stay in the environment or a gitignored .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DATA_DIR = BACKEND_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    garmin_personal_api_key: str = ""
    garmin_personal_api_base_url: str = "https://personal.connectapi.garmin.com"
    garmin_sync_lookback_days: int = 90
    garmin_sync_page_size: int = 20
    garmin_sync_max_activities: int = 200
    garmin_sync_interval_minutes: int = 360
    garmin_timeout_seconds: float = 30.0
    garmin_token_cache_path: Path = Field(default=DATA_DIR / "garmin-bearer-token.json")

    openai_api_key: str = ""
    openai_model: str = "gpt-6.1-sol"
    public_app_url: str = "http://127.0.0.1:3010"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    database_url: str = Field(default=f"sqlite:///{DATA_DIR / 'coach.db'}")

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    athlete_display_name: str = "Athlete"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def garmin_key_configured(self) -> bool:
        return bool(self.garmin_personal_api_key.strip())

    @property
    def resolved_database_url(self) -> str:
        prefix = "sqlite:///"
        url = self.database_url
        if not url.startswith(prefix):
            return url
        raw_path = url[len(prefix) :]
        if raw_path == ":memory:" or raw_path.startswith("file:"):
            return url
        path = Path(raw_path)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
