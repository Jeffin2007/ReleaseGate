"""
Health and readiness check endpoints.
Provides liveness monitoring and deep dependency readiness diagnostics.
"""

from fastapi import APIRouter, Response, status
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["Health & Diagnostics"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Liveness Probe",
    description="Returns immediate 200 OK indicating the API server process is alive.",
)
def get_health() -> HealthResponse:
    """Basic process health confirmation."""
    return HealthService.get_liveness()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Dependency Readiness Probe",
    description=(
        "Performs readiness diagnostics on core dependencies (such as PostgreSQL database connectivity). "
        "Returns HTTP 200 when ready to serve traffic, or HTTP 503 if any required dependency is unhealthy."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "All subsystem dependencies are operational and reachable.",
            "model": ReadinessResponse,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "One or more critical dependencies (e.g. database) are unreachable.",
            "model": ReadinessResponse,
        },
    },
)
def get_ready(response: Response) -> ReadinessResponse:
    """Dependency readiness verification."""
    readiness_result, is_ready = HealthService.check_readiness()

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return readiness_result
