"""
Automated unit tests for application settings and fail-fast validation.
"""

import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_default_settings_valid():
    """Verify default settings instantiation succeeds with valid properties."""
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/releasegate_db",
    )
    assert settings.APP_NAME == "ReleaseGate Control Plane API"
    assert settings.API_PORT == 8000
    assert settings.API_PREFIX == "/api/v1"
    assert settings.DB_POOL_PRE_PING is True


def test_api_prefix_normalization():
    """Verify that api_prefix strips trailing slashes and ensures leading slash."""
    settings = Settings(
        API_PREFIX="api/v2/",
        DATABASE_URL="sqlite:///:memory:",
    )
    assert settings.API_PREFIX == "/api/v2"


def test_invalid_database_url_scheme_fails():
    """Verify fail-fast rejection for unsupported database protocols."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(DATABASE_URL="mysql://root:secret@localhost:3306/db")
    assert "Unsupported database scheme" in str(exc_info.value)


def test_production_fails_with_insecure_secret_key():
    """Verify fail-fast check when in production mode with default/insecure SECRET_KEY."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="change-this-default-secret",
            DATABASE_URL="postgresql+psycopg2://user:pass@db:5432/db",
        )
    assert "CRITICAL CONFIGURATION ERROR" in str(exc_info.value)
    assert "SECRET_KEY" in str(exc_info.value)


def test_production_fails_with_sqlite():
    """Verify fail-fast check prevents using SQLite in production mode (original test)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-long-production-grade-cryptographic-secret-key-12345",
            DATABASE_URL="sqlite:///prod.db",
        )
    assert "Production environment does not permit SQLite databases" in str(exc_info.value)


def test_production_fails_with_sqlite_and_valid_secret():
    """Verify SQLite rejection when SECRET_KEY is a genuinely valid cryptographic production token."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="c8f9b2d4e1a7f053982461bcd9e7428f5a1e3b609c2d87e41fa8b52c03e91d64",
            DATABASE_URL="sqlite:///prod.db",
        )
    error_msg = str(exc_info.value)
    assert "Production environment does not permit SQLite databases" in error_msg
    # Ensure it failed purely on SQLite database URL, not on SECRET_KEY validation
    assert "SECRET_KEY" not in error_msg


def test_production_succeeds_with_strong_config():
    """Verify production settings succeed when strict production requirements are met."""
    settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="super-secret-random-hex-string-for-production-compliance-987654321",
        DATABASE_URL="postgresql+psycopg2://prod_user:strong_password@prod_db:5432/releasegate_prod",
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.SECRET_KEY.startswith("super-secret")
