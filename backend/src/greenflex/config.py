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
    model_cache: Path = Path(r"D:\GreenFlex\models")
    simulation_clock_scale: int = Field(default=1, ge=1, le=3600)
    log_level: str = "INFO"

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("sqlite+aiosqlite", "sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
