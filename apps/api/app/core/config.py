"""
Centralized environment-based application configuration using Pydantic Settings.
Adheres to 12-factor application principles and Frozen Baseline v1.0.
"""

from functools import lru_cache
from typing import List, Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized settings for ReleaseGate FastAPI Control Plane.
    Values are loaded from environment variables with fallback defaults for local development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application identity
    APP_NAME: str = Field(default="ReleaseGate Control Plane API")
    APP_VERSION: str = Field(default="0.1.0")
    ENVIRONMENT: Literal["development", "staging", "production", "testing"] = Field(
        default="development"
    )
    DEBUG: bool = Field(default=False)

    # Server networking
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000, ge=1, le=65535)
    API_PREFIX: str = Field(default="/api/v1")

    # Security & CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    SECRET_KEY: str = Field(
        default="releasegate-dev-insecure-secret-key-change-in-production-12345"
    )

    # Database configuration (PostgreSQL via SQLAlchemy 2.0)
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/releasegate_db"
    )
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1)
    DB_POOL_PRE_PING: bool = Field(default=True)
    DB_ECHO: bool = Field(default=False)

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    LOG_FORMAT: Literal["text", "json"] = Field(default="text")
    REDACT_SENSITIVE_LOGS: bool = Field(default=True)

    # Health check & timeouts
    DB_READINESS_TIMEOUT_SECONDS: float = Field(default=3.0, gt=0.0)

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate that database URL uses a supported SQL engine."""
        v = v.strip()
        supported_prefixes = ("postgresql://", "postgresql+psycopg2://", "sqlite://")
        if not v.startswith(supported_prefixes):
            raise ValueError(
                f"Unsupported database scheme in DATABASE_URL: must start with postgresql://, "
                f"postgresql+psycopg2://, or sqlite:// (for test isolation). Received: {v[:15]}..."
            )
        return v

    @field_validator("API_PREFIX")
    @classmethod
    def validate_api_prefix(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("/"):
            v = f"/{v}"
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_production_constraints(self) -> "Settings":
        """Fail-fast check for production deployments."""
        if self.ENVIRONMENT == "production":
            errors = []

            # 1. Reject SQLite in production environments
            if "sqlite" in self.DATABASE_URL.lower():
                errors.append(
                    "CRITICAL CONFIGURATION ERROR: Production environment does not permit SQLite databases. "
                    "A valid PostgreSQL DATABASE_URL must be configured."
                )

            # 2. Require a strong, non-default cryptographic secret key of at least 32 chars
            insecure_secret_markers = (
                "change-this",
                "dev-insecure",
                "default",
                "secret-key",
                "placeholder",
                "your-secret",
            )
            if (
                any(marker in self.SECRET_KEY.lower() for marker in insecure_secret_markers)
                or self.SECRET_KEY.startswith("releasegate-dev")
                or len(self.SECRET_KEY) < 32
            ):
                errors.append(
                    "CRITICAL CONFIGURATION ERROR: Production environment requires a strong, "
                    "non-default SECRET_KEY of at least 32 characters."
                )

            if errors:
                raise ValueError("\n".join(errors))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()


# Module-level instance for direct imports
settings = get_settings()
