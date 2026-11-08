"""Application settings, loaded from environment / .env file.

Local development uses safe defaults (SQLite, placeholder secrets). In
production (APP_ENV=production) every secret must be supplied via environment
variables and startup fails fast if any required value is missing, left at its
insecure default, or if SQLite is used. Secrets are mapped from Google Secret
Manager into env vars by Cloud Run — this module never reads Secret Manager
directly.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# Insecure placeholder values that must never reach production.
_INSECURE_DEFAULTS = {
    "jwt_secret": "change-me-dev-only",
    "verify_token": "dev-verify-token",
}


class ConfigError(RuntimeError):
    """Raised when production configuration is missing or insecure."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # "local" (default) or "production". Cloud Run sets APP_ENV=production.
    app_env: str = "local"

    database_url: str = "sqlite:///./local-data/aid.sqlite3"

    jwt_secret: str = "change-me-dev-only"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    # WhatsApp webhook config (verification + signature check).
    whatsapp_token: str = ""
    app_secret: str = ""
    verify_token: str = "dev-verify-token"
    phone_number_id: str = ""

    # WhatsApp send adapter. "fake" (default) captures in memory and contacts no
    # network; "graph" calls the real Meta Graph API. Production defaults to graph.
    whatsapp_adapter: str = "fake"
    whatsapp_api_base: str = "https://graph.facebook.com"
    whatsapp_api_version: str = "v21.0"

    # NGO name used in the Step 1 canned greeting ("Somos <name>."). Step 2 will
    # resolve the real org from the receiving phone_number_id instead.
    pilot_org_name: str = "la ONG"

    # Demo seed credentials. Password is REQUIRED in production (no default) so
    # a hardcoded value is never shipped; local dev falls back to a dev value.
    seed_demo_password: str = ""

    # Worker polling loop tuning.
    worker_poll_interval_seconds: float = 5.0
    worker_batch_size: int = 20

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate_runtime(self) -> None:
        """Fail fast on insecure/missing production config.

        Called once at process startup (API and worker). A no-op in local dev.
        """
        if not self.is_production:
            return

        missing: list[str] = []

        if not self.database_url or self.database_url.startswith("sqlite"):
            missing.append("DATABASE_URL (must be a non-SQLite Postgres URL in production)")

        for field, insecure in _INSECURE_DEFAULTS.items():
            value = getattr(self, field)
            if not value or value == insecure:
                missing.append(field.upper())

        # Webhook secrets required to verify and reply to Meta in production.
        for field in ("app_secret", "whatsapp_token", "phone_number_id"):
            if not getattr(self, field):
                missing.append(field.upper())

        if not self.seed_demo_password:
            missing.append("SEED_DEMO_PASSWORD")

        if missing:
            raise ConfigError(
                "Missing or insecure production configuration: "
                + ", ".join(sorted(set(missing)))
                + ". Set these environment variables (mapped from Secret Manager)."
            )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
