"""
Service layer encapsulating service health and dependency readiness checks.
"""

from typing import Tuple
from app.core.config import get_settings
from app.db.session import check_db_connection
from app.schemas.health import HealthResponse, ReadinessCheckItem, ReadinessResponse

settings = get_settings()


class HealthService:
    """Service provider for system liveness and dependency readiness."""

    @staticmethod
    def get_liveness() -> HealthResponse:
        """
        Generate process-level liveness confirmation.
        Returns basic operational status without pinging external dependencies.
        """
        return HealthResponse(
            status="ok",
            app_name=settings.APP_NAME,
            version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT,
        )

    @staticmethod
    def check_readiness() -> Tuple[ReadinessResponse, bool]:
        """
        Perform deep dependency health checks (e.g., PostgreSQL connection).

        Returns:
            Tuple of (ReadinessResponse, is_ready: bool)
        """
        checks = {}
        all_ready = True

        # Check PostgreSQL database connectivity
        db_connected, latency_ms, db_error = check_db_connection(
            timeout_seconds=settings.DB_READINESS_TIMEOUT_SECONDS
        )

        if db_connected:
            checks["database"] = ReadinessCheckItem(
                status="healthy",
                latency_ms=latency_ms,
                details="PostgreSQL connection established and verified via ping query.",
            )
        else:
            checks["database"] = ReadinessCheckItem(
                status="unhealthy",
                latency_ms=latency_ms,
                details=f"Database unreachable: {db_error}",
            )
            all_ready = False

        overall_status = "ready" if all_ready else "not_ready"
        response = ReadinessResponse(
            status=overall_status,
            checks=checks,
        )

        return response, all_ready
