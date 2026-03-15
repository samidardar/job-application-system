import sys
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# Weak default used ONLY during local development — never in production
_DEV_SECRET = "dev-secret-key-change-in-production-must-be-32-chars"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "Postulio"
    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://postulio:postulio_dev_password@localhost:5432/postulio"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = _DEV_SECRET
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    algorithm: str = "HS256"

    @field_validator("secret_key")
    @classmethod
    def secret_key_strong_enough(cls, v: str) -> str:
        if len(v) < 32:
            print(
                "FATAL: SECRET_KEY must be at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"",
                file=sys.stderr,
            )
            raise ValueError("SECRET_KEY too short (min 32 chars)")
        return v

    # Anthropic — Claude Haiku 4.5 (cheapest, ~$0.08/MTok input)
    anthropic_api_key: str = ""

    # France Travail API (ex Pôle Emploi) — https://francetravail.io/data/api
    france_travail_client_id: str = ""
    france_travail_client_secret: str = ""

    # Email (optional)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Storage
    storage_path: str = "/app/storage"

    # Pipeline defaults
    default_min_match_score: int = 70
    default_daily_application_limit: int = 20
    pipeline_hour_utc: int = 7  # 8h00 Paris = 7h00 UTC


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
