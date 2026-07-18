"""Application configuration, loaded from environment / .env (never hard-coded secrets)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"


class Settings(BaseSettings):
    """Runtime configuration.

    All values are overridable via ``CHARWATCH_*`` environment variables or a ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_prefix="CHARWATCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Providers ---
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openrouter_api_key: str | None = None

    # --- Persistence ---
    database_url: str = "sqlite+aiosqlite:///./data/charwatch.db"

    # --- Judge panel ---
    # NoDecode: take the raw env string (e.g. "gpt-4.1,gpt-4o") and let _split_csv parse it,
    # instead of pydantic-settings trying to JSON-decode a list field.
    judge_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["gpt-4.1", "gpt-4o"]
    )

    # --- Sampling / concurrency ---
    samples_per_case: int = Field(default=20, ge=1, le=1000)
    max_concurrency: int = Field(default=8, ge=1, le=64)
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=4, ge=0, le=10)

    # --- Benchmarks ---
    benchmarks_dir: Path = DEFAULT_BENCHMARKS_DIR

    # --- Scheduler (recurring evaluations) ---
    enable_scheduler: bool = True

    # --- Logging ---
    log_format: str = "console"  # "console" | "json"
    log_level: str = "INFO"

    @field_validator("judge_models", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow comma-separated strings for list fields (e.g. CHARWATCH_JUDGE_MODELS)."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
