from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "RegBite"
    debug: bool = False

    # Database
    database_url: str = "postgresql://regbite:regbite@localhost:5432/regbite"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "change-this-secret"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    # Anthropic (Claude) — used for label extraction
    anthropic_api_key: str = ""

    # OpenRouter — used for Gemma 4 (and any future OpenRouter models)
    openrouter_api_key: str = ""                     # sk-or-... from openrouter.ai/keys
    openrouter_api_url: str = "https://openrouter.ai/api/v1"

    # Gemma via OpenRouter — use Browse OpenRouter Models on /admin/llm to find exact slug
    gemma_model_name: str = "google/gemma-4-31b-it"  # OpenRouter model ID (override with GEMMA_MODEL_NAME)
    gemma_enabled: bool = True                        # killswitch — set False to skip Gemma
    gemma_visual_token_budget: int = 560              # 560=standard, 1120=detailed fine-print

    # Legacy vLLM fields (kept for backwards compat, no longer used)
    gemma_api_url: str = ""
    gemma_api_key: str = ""

    # Email (Brevo SMTP)
    brevo_smtp_host: str = "smtp-relay.brevo.com"
    brevo_smtp_port: int = 587
    brevo_smtp_user: str = ""
    brevo_smtp_password: str = ""
    alert_from_email: str = "alerts@regbite.local"
    alert_to_email: str = ""

    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Sentry error monitoring
    sentry_dsn: str = ""   # set SENTRY_DSN env var in Railway

    # Admin
    admin_email: str = ""

    # Public base URL — used in notification emails so links resolve correctly.
    # Override with APP_BASE_URL env var in staging/production environments.
    app_base_url: str = "https://regbite.com"

    # Database pool — sized for parallel KB uploads (4 concurrent) + web requests
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 15
    db_statement_timeout: int = 30000  # ms

    # File uploads
    upload_dir: str = "./uploads"

    # Local extraction (reduces Claude API calls)
    local_extraction_enabled: bool = True
    local_extraction_min_confidence: float = 0.72

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
