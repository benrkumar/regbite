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
    access_token_expire_minutes: int = 480

    # Gemini
    gemini_api_key: str = ""

    # Email (Brevo SMTP)
    brevo_smtp_host: str = "smtp-relay.brevo.com"
    brevo_smtp_port: int = 587
    brevo_smtp_user: str = ""
    brevo_smtp_password: str = ""
    alert_from_email: str = "alerts@regbite.local"
    alert_to_email: str = ""

    # File uploads
    upload_dir: str = "./uploads"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
