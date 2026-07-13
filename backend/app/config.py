"""Centralized application configuration.

All secrets and tunable parameters are loaded from a ``.env`` file (or real
environment variables) via ``pydantic-settings``. Nothing is hardcoded here.

Usage::

    from app.config import get_settings
    settings = get_settings()
    settings.anthropic_api_key  # doctest: +SKIP

``get_settings()`` is cached for the process lifetime via ``functools.lru_cache``,
so repeated calls are cheap and return the same object.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve paths relative to this file so the app works regardless of CWD.
BACKEND_ROOT = Path(__file__).resolve().parent.parent          # .../backend
APP_ROOT = Path(__file__).resolve().parent.parent.parent        # .../industrial-knowledge-brain


class Settings(BaseSettings):
    """Strongly-typed settings loaded from environment / ``.env``.

    Every field has a sensible dev default so the app can boot even before a
    real ``.env`` exists; external-service calls (Claude, Neo4j, Postgres)
    simply fail gracefully with a clear error when the placeholder values are
    still in place.
    """

    model_config = SettingsConfigDict(
        # Single project-root .env for both Docker and local `uvicorn` dev.
        env_file=str(APP_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # App
    # ------------------------------------------------------------------ #
    app_name: str = "Industrial Knowledge Brain"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> list[str]:
        """Accept either a JSON array string or a real list from the env."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except json.JSONDecodeError:
                # comma-separated fallback
                return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return [str(x) for x in v]
        return ["*"]

    # ------------------------------------------------------------------ #
    # Google Gemini (LLM + entity extraction)
    # ------------------------------------------------------------------ #
    gemini_api_key: str = "REPLACE_ME"
    gemini_model: str = "gemini-2.5-flash"
    gemini_max_tokens: int = 4096
    llm_provider: str = "gemini"

    # ------------------------------------------------------------------ #
    # Neo4j
    # ------------------------------------------------------------------ #
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "REPLACE_ME"

    # ------------------------------------------------------------------ #
    # ChromaDB
    # ------------------------------------------------------------------ #
    chroma_persist_dir: str = str(BACKEND_ROOT / "data" / "chroma_persist")
    chroma_collection_name: str = "documents"

    # ------------------------------------------------------------------ #
    # PostgreSQL / Supabase
    # ------------------------------------------------------------------ #
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "postgres"
    postgres_user: str = "postgres"
    postgres_password: str = "REPLACE_ME"
    postgres_sslmode: str = "prefer"

    @property
    def postgres_dsn(self) -> str:
        """Async-ready SQLAlchemy DSN for the configured Postgres."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"?sslmode={self.postgres_sslmode}"
        )

    # ------------------------------------------------------------------ #
    # OCR
    # ------------------------------------------------------------------ #
    ocr_fallback_enabled: bool = True
    ocr_language: str = "eng"
    ocr_min_text_len: int = 20

    # ------------------------------------------------------------------ #
    # Voice
    # ------------------------------------------------------------------ #
    bhashini_api_url: str = "https://dhruva-api.bhashini.gov.in/services/v1/translate"
    bhashini_api_key: str = "REPLACE_ME"
    bhashini_user_id: str = "REPLACE_ME"
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # ------------------------------------------------------------------ #
    # Auth / JWT
    # ------------------------------------------------------------------ #
    jwt_secret: str = "CHANGE_ME_TO_A_LONG_RANDOM_STRING"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    # ------------------------------------------------------------------ #
    # Derived helpers
    # ------------------------------------------------------------------ #
    @property
    def is_dev(self) -> bool:
        """True when running outside production (controls CORS strictness, etc.)."""
        return self.app_env.lower() != "production"

    @property
    def chroma_path(self) -> Path:
        """ChromaDB persistence directory as a resolved ``Path``."""
        p = Path(self.chroma_persist_dir)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton for this process."""
    return Settings()
