"""
Pydantic schemas for Inspection Runs and Findings persistence.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.db.models.inspection import FindingType, InspectionStatus, InspectionType


class FindingCreate(BaseModel):
    """Payload to record an individual finding discovered during an inspection."""
    finding_type: FindingType
    category: str = Field(min_length=1, max_length=64, description="Entity type or rule name (e.g. EMAIL_ADDRESS, NOT_NULL)")
    column_name: Optional[str] = Field(default=None, max_length=255)
    severity: str = Field(description="Severity tier: CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL")
    occurrence_count: int = Field(default=1, ge=1)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    message: str = Field(min_length=1)
    evidence_ref: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured coordinates, distributions, and hashes with ZERO raw values",
    )


class FindingResponse(BaseModel):
    """Finding response record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    inspection_run_id: UUID
    dataset_version_id: UUID
    finding_type: str
    category: str
    column_name: Optional[str]
    severity: str
    occurrence_count: int
    confidence_score: Optional[float]
    message: str
    evidence_ref: Dict[str, Any]
    created_at: datetime


class InspectionRunCreate(BaseModel):
    """Payload to create an inspection run record."""
    dataset_id: UUID
    dataset_version_id: UUID
    inspection_type: InspectionType = InspectionType.FULL_SCAN
    status: InspectionStatus = InspectionStatus.COMPLETED
    risk_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    risk_band: Optional[str] = None
    policy_version: Optional[str] = None
    is_release_eligible: Optional[bool] = None
    summary_report: Dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregate summary report with zero raw dataset values",
    )
    findings: List[FindingCreate] = Field(default_factory=list)


class InspectionRunResponse(BaseModel):
    """Inspection run response record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID
    inspection_type: str
    status: str
    risk_score: Optional[float]
    risk_band: Optional[str]
    policy_version: Optional[str]
    is_release_eligible: Optional[bool]
    summary_report: Dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime]
    findings_count: int = 0
    findings: List[FindingResponse] = Field(default_factory=list)
