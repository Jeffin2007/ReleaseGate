"""
Automated tests for /health and /ready service endpoints.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient


def test_health_root_endpoint(client: TestClient):
    """Verify that root GET /health returns 200 OK with expected payload schema."""
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert "app_name" in payload
    assert "version" in payload
    assert payload["environment"] == "testing"
    assert "timestamp" in payload


def test_health_prefixed_endpoint(client: TestClient):
    """Verify that versioned GET /api/v1/health returns 200 OK with expected payload schema."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "testing"


def test_ready_endpoint_healthy(client: TestClient):
    """Verify that GET /ready returns 200 OK when database dependency is healthy."""
    with patch("app.services.health_service.check_db_connection") as mock_ping:
        mock_ping.return_value = (True, 1.25, None)

        response = client.get("/ready")
        assert response.status_code == 200

        payload = response.json()
        assert payload["status"] == "ready"
        assert "database" in payload["checks"]
        assert payload["checks"]["database"]["status"] == "healthy"
        assert payload["checks"]["database"]["latency_ms"] == 1.25


def test_ready_endpoint_unhealthy_returns_503(client: TestClient):
    """Verify that GET /ready returns 503 Service Unavailable when database dependency fails."""
    with patch("app.services.health_service.check_db_connection") as mock_ping:
        mock_ping.return_value = (False, 3000.0, "OperationalError: Connection refused")

        response = client.get("/ready")
        assert response.status_code == 503

        payload = response.json()
        assert payload["status"] == "not_ready"
        assert "database" in payload["checks"]
        assert payload["checks"]["database"]["status"] == "unhealthy"
        assert "Connection refused" in payload["checks"]["database"]["details"]
