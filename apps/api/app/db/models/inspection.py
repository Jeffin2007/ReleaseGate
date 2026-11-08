"""
SQLAlchemy 2.0 models for InspectionRuns and Findings.
Persists inspection execution results, risk scores, and granular findings.
Connects findings to immutable dataset versions and inspection runs.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.dataset import Dataset, DatasetVersion
    from app.db.models.identity import Organization


class InspectionType(str, Enum):
    """Categorization of dataset inspection executions."""
    FULL_SCAN = "FULL_SCAN"
    PII_DETECTION = "PII_DETECTION"
    QUALITY_VALIDATION = "QUALITY_VALIDATION"
    POLICY_EVALUATION = "POLICY_EVALUATION"


class InspectionStatus(str, Enum):
    """Lifecycle status of an inspection run."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FindingType(str, Enum):
    """Classification of findings recorded during inspection."""
    PII = "PII"
    QUALITY = "QUALITY"
    POLICY = "POLICY"
    PROVENANCE = "PROVENANCE"


class InspectionRun(Base):
    """
    Execution record for a dataset inspection.
    Tracks risk scores, release policy evaluation outcomes, and links to findings.
    """
    __tablename__ = "inspection_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inspection_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=InspectionType.FULL_SCAN.value,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=InspectionStatus.COMPLETED.value,
        index=True,
    )
    risk_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    risk_band: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    policy_version: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    is_release_eligible: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )
    summary_report: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Sanitized aggregate inspection summary; zero raw dataset values.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="inspection_runs",
    )
    dataset: Mapped["Dataset"] = relationship(
        "Dataset",
        back_populates="inspection_runs",
    )
    dataset_version: Mapped["DatasetVersion"] = relationship(
        "DatasetVersion",
        back_populates="inspection_runs",
    )
    findings: Mapped[List["Finding"]] = relationship(
        "Finding",
        back_populates="inspection_run",
        cascade="all, delete-orphan",
    )


class Finding(Base):
    """
    Individual sensitive, quality, or policy issue discovered during an inspection.
    Preserves opaque coordinates, statistical summaries, and evidence hashes with zero raw values.
    """
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inspection_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    column_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    evidence_ref: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Structured evidence coordinates, sample row indices, length distributions, and SHA-256 evidence hash. ZERO raw values.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    inspection_run: Mapped["InspectionRun"] = relationship(
        "InspectionRun",
        back_populates="findings",
    )
    dataset_version: Mapped["DatasetVersion"] = relationship(
        "DatasetVersion",
        back_populates="findings",
    )
