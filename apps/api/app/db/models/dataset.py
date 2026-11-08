"""
SQLAlchemy 2.0 models for Dataset and immutable DatasetVersion.
Adheres to ReleaseGate Architecture Baseline v1.0 entity specifications.
Preserves existing fields, constraints, and relationships while establishing
multi-tenant organization linkages and inspection persistence connections.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.identity import Organization, User
    from app.db.models.inspection import Finding, InspectionRun


class Dataset(Base):
    """
    Top-level dataset container record.
    Tracks high-level metadata, organizational ownership, and active version reference.
    """

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="datasets",
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="created_datasets",
    )
    versions: Mapped[List["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version_number",
    )
    inspection_runs: Mapped[List["InspectionRun"]] = relationship(
        "InspectionRun",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


class DatasetVersion(Base):
    """
    Immutable dataset version artifact record.
    Enforces cryptographic content hashing and opaque secure file references.
    Once registered, records cannot be altered.
    """

    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 hex string
        nullable=False,
        index=True,
    )
    file_format: Mapped[str] = mapped_column(
        String(32),  # csv, xlsx, json
        nullable=False,
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    local_artifact_ref: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Opaque secure reference (artifact://local/datasets/...); never an absolute host path.",
    )
    dataset_metadata: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        comment="Deterministic profiling metadata: row_count, columns, nulls, duplicates.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship(
        "Dataset",
        back_populates="versions",
    )
    inspection_runs: Mapped[List["InspectionRun"]] = relationship(
        "InspectionRun",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
    )
    findings: Mapped[List["Finding"]] = relationship(
        "Finding",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
    )
