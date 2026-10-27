from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "TaskFlow"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Security & JWT
    SECRET_KEY: str = "taskflow-super-secret-key-change-in-production-min32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database
    DATABASE_URL: str = "postgresql://taskflow:taskflow_password@localhost:5432/taskflow_db"
    # When testing or developing without Postgres running, can fall back to sqlite
    USE_SQLITE_FALLBACK: bool = True
    SQLITE_DB_PATH: str = "taskflow.db"

    # Redis Cache & Broker
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes
    CACHE_VERSION_TTL: int = 86400  # 24 hours for cache version keys

    # Celery Background Processing
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    OVERDUE_TASK_CHECK_INTERVAL_SECONDS: int = 60

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def get_celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    def get_celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    def get_effective_database_url(self) -> str:
        """Returns the appropriate database URL based on environment or fallback."""
        if self.ENVIRONMENT == "testing":
            return "sqlite:///./test_taskflow.db"
        return self.DATABASE_URL


settings = Settings()
