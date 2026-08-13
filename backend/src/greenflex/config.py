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

    # --- Real-time carbon intensity ---
    electricity_maps_api_key: str | None = None
    carbon_intensity_region: str = "CN-HN"  # Hunan/Changsha default
    electricity_maps_zone: str = "CN-CS"  # China Central-South grid zone
    carbon_intensity_cache_ttl_minutes: int = Field(default=15, ge=5, le=1440)
    carbon_provider_chain: str = "electricity_maps,dynlca,fallback"

    # --- Energy estimation ---
    local_gpu_model: str = "rtx-3060-laptop"
    energy_estimator_enabled: bool = True
    auto_calibrate_gpu: bool = True

    # RL Router (v2)
    rl_router_enabled: bool = True
    rl_router_mode: str = "shadow"  # disabled, shadow, advisory, autonomous
    rl_router_policy_path: str = "data/rl_policy.json"

    # C2PA (v2)
    c2pa_secret_key: str = "greenflex-local"
    c2pa_enabled: bool = True

    # AI Act Compliance (v2)
    ai_act_compliance_enabled: bool = True

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("sqlite+aiosqlite", "sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
