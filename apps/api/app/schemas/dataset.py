"""
Pydantic schemas for dataset ingestion, profiling, and version inspection.
Exposes only secure artifact references and sanitized profiling metadata.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class DatasetProfileSchema(BaseModel):
    """Deterministic tabular profiling statistics."""
    model_config = ConfigDict(from_attributes=True)

    row_count: int = Field(ge=0, description="Total number of records in dataset")
    column_count: int = Field(ge=0, description="Total number of schema attributes/columns")
    columns: List[str] = Field(description="Ordered list of column names")
    column_types: Dict[str, str] = Field(description="Inferred normalized semantic types per column")
    null_counts: Dict[str, int] = Field(description="Missing/null value count per column")
    null_percentages: Dict[str, float] = Field(description="Percentage of null values per column (0.0 to 100.0)")
    duplicate_row_count: int = Field(ge=0, description="Count of duplicate rows detected")
    file_format: str = Field(description="Normalized file format: csv, xlsx, or json")


class DatasetVersionResponse(BaseModel):
    """Immutable dataset version record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Unique version identifier")
    dataset_id: UUID = Field(description="Parent dataset container identifier")
    version_number: int = Field(ge=1, description="Sequential version index")
    content_hash: str = Field(description="Cryptographic SHA-256 binary hash digest")
    file_format: str = Field(description="Format extension: csv, xlsx, json")
    file_size: int = Field(ge=0, description="Payload size in bytes")
    local_artifact_ref: str = Field(
        description="Opaque secure artifact reference (artifact://local/datasets/...); never an absolute filesystem path"
    )
    metadata: DatasetProfileSchema = Field(
        alias="metadata",
        description="Deterministic profiling metrics",
    )
    created_at: datetime = Field(description="Creation UTC timestamp")


class DatasetResponse(BaseModel):
    """Top-level dataset model response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Unique dataset identifier")
    organization_id: Optional[UUID] = Field(default=None, description="Workspace/tenant identifier")
    name: str = Field(description="Human-readable dataset name")
    description: Optional[str] = Field(default=None, description="Dataset description or notes")
    current_version_id: Optional[UUID] = Field(default=None, description="Reference to latest active version")
    created_at: datetime = Field(description="Creation UTC timestamp")
    versions: List[DatasetVersionResponse] = Field(
        default_factory=list,
        description="History of immutable dataset versions",
    )


class DatasetIngestResponse(BaseModel):
    """Detailed response after successful ingestion and profiling."""
    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    dataset_name: str
    version_id: UUID
    version_number: int
    content_hash: str
    local_artifact_ref: str
    profile: DatasetProfileSchema
    message: str = "Dataset successfully ingested, cryptographically hashed, and profiled locally."
