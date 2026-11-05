"""
Pydantic schemas for health and readiness response models.
"""

from datetime import datetime, timezone
from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Basic service health status payload."""
    status: Literal["ok", "degraded", "error"] = Field(
        default="ok",
        description="Current operational status of the service process",
    )
    app_name: str = Field(description="Name of the service application")
    version: str = Field(description="Service semantic release version")
    environment: str = Field(description="Runtime environment identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the health observation",
    )


class ReadinessCheckItem(BaseModel):
    """Status details for an individual subsystem dependency."""
    status: Literal["healthy", "unhealthy"] = Field(
        description="Health status of this dependency"
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Measured latency for pinging the dependency in milliseconds",
    )
    details: Optional[str] = Field(
        default=None,
        description="Optional diagnostic description or error details",
    )


class ReadinessResponse(BaseModel):
    """Aggregate readiness check response for orchestrators and load balancers."""
    status: Literal["ready", "not_ready"] = Field(
        description="Overall service readiness to accept and process traffic"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the readiness check",
    )
    checks: Dict[str, ReadinessCheckItem] = Field(
        description="Detailed breakdown of evaluated subsystem dependencies"
    )
