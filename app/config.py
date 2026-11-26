"""Configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Project paths
    project_root: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    static_dir: Path = Path(__file__).resolve().parent.parent / "static"

    # Agent behavior
    max_agent_iterations: int = 15
    max_tokens_per_turn: int = 4096

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Singleton settings accessor."""
    return Settings()
