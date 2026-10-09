"""Application configuration.

All configuration is sourced from environment variables (optionally via a
local ``.env`` file) using the ``CLAWSENSE_`` prefix.  No secret is ever
hard-coded here, and nothing in this module is exposed to the browser bundle.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_prefix="CLAWSENSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Application mode ---------------------------------------------------
    #: "simulation" (deterministic simulator, no hardware) or "hardware".
    app_mode: str = "simulation"

    # -- Server / persistence ----------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "./data/clawsense.sqlite3"

    # -- Agent / LLM --------------------------------------------------------
    agent_provider: str = "simulated"  # simulated | espclaw
    agent_timeout_seconds: float = 10.0
    espclaw_endpoint: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # -- Device communication ----------------------------------------------
    device_transport: str = "simulated"  # simulated | http
    device_base_url: str = "http://192.168.0.50"
    device_id: str = "esp32s3-clawsense-01"
    device_command_timeout_seconds: float = 5.0
    device_retry_attempts: int = 2
    #: Commands older than this are considered stale and must not execute.
    command_ttl_seconds: float = 10.0

    # -- Timeouts / health --------------------------------------------------
    degraded_timeout_seconds: float = 15.0
    offline_timeout_seconds: float = 45.0
    context_max_age_seconds: float = 30.0

    # -- Sensor thresholds --------------------------------------------------
    temp_high_c: float = 35.0
    temp_low_c: float = 5.0
    humidity_high_percent: float = 80.0

    # -- Safety -------------------------------------------------------------
    servo_min_degrees: int = 0
    servo_max_degrees: int = 180
    buzzer_max_ms: int = 2000
    action_cooldown_seconds: float = 3.0
    rate_limit_max: int = 6
    rate_limit_window_seconds: float = 30.0
    allowed_actions: list[str] = Field(
        default_factory=lambda: [
            "servo_move",
            "buzzer_beep",
            "set_status_led",
            "no_op",
        ]
    )

    # -- Simulator cadence --------------------------------------------------
    simulator_interval_seconds: float = 2.0
    #: When true the in-process simulated device/sensor loop runs on startup.
    simulator_enabled: bool = True

    @field_validator("allowed_actions", mode="before")
    @classmethod
    def _split_allowed_actions(cls, value: object) -> object:
        """Allow ``CLAWSENSE_ALLOWED_ACTIONS=a,b,c`` style configuration."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("app_mode")
    @classmethod
    def _validate_app_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"simulation", "hardware"}:
            raise ValueError("app_mode must be 'simulation' or 'hardware'")
        return value

    @field_validator("agent_provider")
    @classmethod
    def _validate_agent_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"simulated", "espclaw"}:
            raise ValueError("agent_provider must be 'simulated' or 'espclaw'")
        return value

    @field_validator("device_transport")
    @classmethod
    def _validate_device_transport(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"simulated", "http"}:
            raise ValueError("device_transport must be 'simulated' or 'http'")
        return value

    # -- Derived helpers ----------------------------------------------------
    @property
    def is_simulation(self) -> bool:
        return self.app_mode == "simulation"

    @property
    def db_file(self) -> Path:
        return Path(self.db_path)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
