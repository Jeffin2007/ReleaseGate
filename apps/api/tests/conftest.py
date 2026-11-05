"""
Pytest configuration and shared fixtures for ReleaseGate API tests.
"""

import os
import pytest
from fastapi.testclient import TestClient

# Ensure test environment before loading application
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-local-pytest-suite-only"
os.environ["REDACT_SENSITIVE_LOGS"] = "true"

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear settings lru_cache between test runs."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a synchronous TestClient."""
    with TestClient(app) as test_client:
        yield test_client
