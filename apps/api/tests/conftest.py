"""
Pytest configuration and shared fixtures for ReleaseGate API tests.
"""

import os
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure test environment before loading application
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-local-pytest-suite-only"
os.environ["REDACT_SENSITIVE_LOGS"] = "true"

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app as fastapi_app
from app.db import models  # Register models with Base.metadata
from local_worker.secure_storage import LocalDatasetStorage


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear settings lru_cache between test runs."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def setup_test_database():
    """Initialize test in-memory database schema before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Isolated database session fixture for service tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def temp_storage():
    """Isolated temporary dataset storage directory for testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_datasets_"))
    storage = LocalDatasetStorage(base_dir=temp_dir)
    yield storage
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a synchronous TestClient."""
    with TestClient(fastapi_app) as test_client:
        yield test_client
