"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    app_name: str = "Fineract AML Service"
    app_version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://aml:aml@localhost:5432/fineract_aml"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Fineract
    fineract_base_url: str = "https://localhost:8443/fineract-provider/api/v1"
    fineract_webhook_secret: str = "change-me-in-production"

    # ML
    model_path: str = "./models"
    anomaly_threshold: float = 0.7
    risk_score_high: float = 0.8
    risk_score_medium: float = 0.5

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment_name: str = "fineract-aml"

    # Auth
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Currency
    default_currency: str = "XAF"

    # Rule engine
    max_transaction_amount: float = 10000.0
    rapid_transaction_window_minutes: int = 60
    rapid_transaction_count: int = 10
    structuring_threshold: float = 9500.0
    new_account_age_days: int = 30

    model_config = {"env_file": ".env", "env_prefix": "AML_"}


settings = Settings()
