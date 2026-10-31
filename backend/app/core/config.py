"""Application configuration loaded from environment / .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ---- General ----
    app_name: str = "QuoteFlow"
    app_version: str = "1.0.0"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # ---- Database ----
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "quoteflow"

    # ---- Security ----
    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    verification_secret: str = "change-me-verification-secret"

    # ---- CORS ----
    #: Comma-separated in the environment. Kept as a string because
    #: pydantic-settings JSON-decodes list-typed fields before validation runs,
    #: which would reject a plain comma-separated value.
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    # ---- Storage ----
    pdf_storage_dir: str = "storage/quotations"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
        ]

    @property
    def pdf_storage_path(self) -> Path:
        path = Path(self.pdf_storage_dir)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so the .env file is parsed once per process."""
    return Settings()


settings = get_settings()
