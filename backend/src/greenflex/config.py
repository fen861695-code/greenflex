from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GREENFLEX_",
        extra="ignore",
    )

    env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: str = "http://127.0.0.1:5173"
    database_url: str = "sqlite+aiosqlite:///./data/greenflex.db"
    artifact_dir: Path = Path("./artifacts")
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_connect_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    ollama_request_timeout_seconds: float = Field(default=300.0, gt=0, le=900)
    model_cache: Path = Path(r"D:\GreenFlex\models")
    telemetry_interval_ms: int = Field(default=500, ge=250, le=5_000)
    telemetry_idle_seconds: float = Field(default=3.0, ge=0.5, le=10)
    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=30)
    worker_lease_seconds: int = Field(default=600, ge=60, le=3_600)
    simulation_clock_scale: int = Field(default=1, ge=1, le=3600)
    log_level: str = "INFO"
    grid_region: str = "CN-East"
    nvml_enabled: bool = False

    # Cloud API keys (all optional; when unset, simulated provider is used)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    deepseek_api_key: str | None = None
    alibaba_api_key: str | None = None
    bytedance_api_key: str | None = None
    google_api_key: str | None = None

    # Cloud API base URL overrides (optional)
    openai_base_url: str | None = None
    anthropic_base_url: str | None = None
    deepseek_base_url: str | None = None
    alibaba_base_url: str | None = None
    bytedance_base_url: str | None = None
    google_base_url: str | None = None

    # Cloud API request timeout
    cloud_api_timeout_seconds: float = Field(default=120.0, gt=5, le=600)

    # Admin token for settings write API (auto-generated if not set)
    admin_token: str | None = None

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("sqlite+aiosqlite", "sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
