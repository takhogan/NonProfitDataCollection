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

    # --- WhatsApp conversation engine (OPW-010..035) ---
    # App-level encryption (DB-050) and lookup HMAC (DB-051) keys: base64, 32
    # bytes each. Required in production; local dev derives non-secret keys.
    data_encryption_key: str = ""
    lookup_hmac_key: str = ""
    # A conversation resumes within this many hours (OPW-017); after that the
    # next message starts a new report.
    conversation_resume_hours: int = 48
    # Free-form replies only inside the 24-hour customer-service window (OPW-031).
    whatsapp_session_window_hours: int = 24
    # Approved Meta templates, JSON: {"report_received": {"name": "...",
    # "language": "es"}, ...}. Registered by the WhatsApp contributor (OPW-033).
    whatsapp_templates_json: str = "{}"
    # Outbound token bucket (OPW-034): sustained sends per second and burst.
    whatsapp_send_rate_per_second: float = 10.0
    whatsapp_send_burst: int = 20
    # Surge mode (OPW-035): when the oldest unprocessed inbound event is older
    # than this, send one holding reply per conversation first.
    surge_lag_seconds: int = 120
    # A send that may have reached Meta (timeout after submission) is never
    # resent blindly (OPW-032). It waits this long for a status webhook that
    # names it; otherwise it becomes a visible failure.
    uncertain_send_reconcile_minutes: int = 15
    # Urgent path referral content (OPW-021, D15). Configured per deployment.
    urgent_referral_text: str = (
        "Si hay riesgo para la vida, contacta a los servicios de emergencia locales "
        "o a un centro de salud cercano."
    )

    # --- Optional OpenAI extraction (amended OPW-023) ---
    # Off by default. When on, ONLY a short typed answer that the deterministic
    # parser could not read is sent, after phone numbers, e-mails and long digit
    # runs are removed. Address answers, names and the sender's number are never
    # sent. The model returns JSON in a fixed schema; code validates it and
    # writes the rows. The model never chooses database ids or writes SQL.
    openai_extraction: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = 15.0

    # --- Staff authentication (API-010..014). Added for the /v1 API. ---
    # The browser origin of the staff web app, e.g. https://app.example.org.
    # Credentialed CORS is allowed from this origin only; empty disables CORS.
    web_origin: str = ""
    # Session cookie. Secure is on by default; set SESSION_COOKIE_SECURE=false
    # only for plain-http local development. With Secure on and no domain, the
    # cookie gets the __Host- prefix (bound to this exact host).
    session_cookie_secure: bool = True
    session_cookie_domain: str = ""
    # SEC-05 timeouts.
    session_idle_timeout_minutes: int = 30
    session_absolute_timeout_hours: int = 12
    # Short window for the password -> TOTP step and the OIDC round trip.
    preauth_timeout_minutes: int = 5
    # Password sign-in lockout.
    password_max_failures: int = 5
    password_lockout_minutes: int = 15
    # Google OIDC. Empty client id disables Google sign-in (404).
    oidc_google_client_id: str = ""
    oidc_google_client_secret: str = ""
    oidc_google_metadata_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    # Absolute callback URL registered with Google, e.g.
    # https://api.example.org/v1/auth/oidc/google/callback
    oidc_google_redirect_uri: str = ""
    # TOTP issuer label shown in authenticator apps (keep neutral, SEC-12).
    totp_issuer: str = "Metron"
    # Rate limits (API-111), per client IP, per minute. In-process counters.
    rate_limit_signin_per_minute: int = 10
    rate_limit_webhook_per_minute: int = 1200
    # Number of trusted proxies that append to X-Forwarded-For (0 = use the
    # socket peer address). Cloud Run's front end appends one hop.
    forwarded_for_trusted_hops: int = 0
    # Structured JSON logs (API-112). Disable for readable local output.
    json_logs: bool = True
    log_level: str = "INFO"

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

        # Conversation data is encrypted at the application layer (DB-050/051).
        for field in ("data_encryption_key", "lookup_hmac_key"):
            if not getattr(self, field):
                missing.append(field.upper())

        if self.openai_extraction and not self.openai_api_key:
            missing.append("OPENAI_API_KEY (OPENAI_EXTRACTION is on)")

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
