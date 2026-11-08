"""Dashboard API settings.

Shares the JWT secret and DATABASE_URL with whatsapp/api so tokens issued by
either are accepted and both read the same database.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"

    # Same DB as whatsapp/api (Step 2 uses it; Step 1 returns fake data).
    database_url: str = "sqlite:///../whatsapp/api/local-data/aid.sqlite3"

    # MUST match whatsapp/api's JWT_SECRET so logins are interoperable.
    jwt_secret: str = "change-me-dev-only"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    # Comma-separated allowed browser origins for the frontend (credentialed CORS).
    web_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.web_origins.split(",") if o.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
