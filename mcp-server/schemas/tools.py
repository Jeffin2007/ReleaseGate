"""
Strict Pydantic argument schemas for all 12 Model Context Protocol (MCP) tools.
Adheres to ReleaseGate Frozen Architecture Baseline v1.0 specifications.
Prevents arbitrary parameter injection and validates types, ranges, and formats.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


# =====================================================================
# Tool 1: inspect_dataset
# =====================================================================
class InspectDatasetArgs(BaseModel):
    """Arguments for inspect_dataset tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Unique dataset identifier (UUID string or registered alias)")
    version_number: int = Field(default=1, ge=1, description="Immutable dataset version number")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("dataset_id cannot be blank")
        return v


# =====================================================================
# Tool 2: detect_sensitive_data
# =====================================================================
class DetectSensitiveDataArgs(BaseModel):
    """Arguments for detect_sensitive_data tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Target dataset identifier")
    version_number: int = Field(default=1, ge=1, description="Immutable dataset version number")
    confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum Presidio detection confidence threshold"
    )
    entities: Optional[List[str]] = Field(
        default=None,
        description="Optional subset of entity types to scan (e.g. ['PERSON', 'EMAIL_ADDRESS', 'PHONE_NUMBER'])",
    )
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 3: validate_data_quality
# =====================================================================
class ValidateDataQualityArgs(BaseModel):
    """Arguments for validate_data_quality tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Target dataset identifier")
    version_number: int = Field(default=1, ge=1, description="Immutable dataset version number")
    allow_nulls: Optional[bool] = Field(
        default=None, description="Override: whether missing/null values are permitted"
    )
    allow_duplicates: Optional[bool] = Field(
        default=None, description="Override: whether duplicate records are permitted"
    )
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 4: check_release_policy
# =====================================================================
class CheckReleasePolicyArgs(BaseModel):
    """Arguments for check_release_policy tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Target dataset identifier")
    version_number: int = Field(default=1, ge=1, description="Immutable dataset version number")
    policy_version: str = Field(default="1.0.0", description="Version of organizational release policy to evaluate against")
    domain: Optional[str] = Field(default=None, description="Operational domain tag (e.g. 'internal_analytics', 'customer_facing')")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 5: generate_risk_report
# =====================================================================
class GenerateRiskReportArgs(BaseModel):
    """Arguments for generate_risk_report tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Target dataset identifier")
    version_number: int = Field(default=1, ge=1, description="Immutable dataset version number")
    policy_version: str = Field(default="1.0.0", description="Policy version used for scoring weights")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 6: propose_transformation
# =====================================================================
class TransformationOperationSpec(BaseModel):
    """Structured allowlisted transformation operation specification."""
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(
        description="Allowlisted operation: 'remove_column', 'mask_column', 'pseudonymize_column', 'generalize_column', 'filter_rows'"
    )
    column: Optional[str] = Field(default=None, description="Target column name")
    columns: Optional[List[str]] = Field(default=None, description="Multiple target columns")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Operation-specific parameters (e.g. mask_char, salt, bins, condition)"
    )

    @field_validator("operation")
    @classmethod
    def validate_allowed_operation(cls, v: str) -> str:
        allowed = {"remove_column", "mask_column", "pseudonymize_column", "generalize_column", "filter_rows"}
        op = v.strip().lower()
        if op not in allowed:
            raise ValueError(f"Operation '{v}' is prohibited. Allowed operations: {sorted(list(allowed))}")
        return op


class ProposeTransformationArgs(BaseModel):
    """Arguments for propose_transformation tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Target dataset identifier")
    version_number: int = Field(default=1, ge=1, description="Base dataset version number")
    operations: List[TransformationOperationSpec] = Field(
        min_length=1, description="List of allowlisted transformation operations to apply"
    )
    rationale: str = Field(min_length=5, description="Governance justification for proposed transformations")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 7: prepare_release
# =====================================================================
class PrepareReleaseArgs(BaseModel):
    """Arguments for prepare_release tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Target dataset identifier")
    source_version_number: int = Field(default=1, ge=1, description="Verified source version number")
    destination_target: str = Field(
        description="Approved release destination (e.g. 's3://analytics-export', 'bigquery://public_release', 'sftp://partner-sync')"
    )
    release_notes: Optional[str] = Field(default=None, description="Summary of dataset contents and release context")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")

    @field_validator("destination_target")
    @classmethod
    def validate_destination_target(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("s3://") or v.startswith("bigquery://") or v.startswith("gcs://") or v.startswith("sftp://") or v.startswith("internal://")):
            raise ValueError("destination_target must use an approved URI protocol: s3://, gcs://, bigquery://, sftp://, internal://")
        return v


# =====================================================================
# Tool 8: submit_for_review
# =====================================================================
class SubmitForReviewArgs(BaseModel):
    """Arguments for submit_for_review tool."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(description="Target dataset identifier")
    version_number: int = Field(default=1, ge=1, description="Dataset version to submit")
    staged_release_id: Optional[str] = Field(default=None, description="Identifier of staged release package")
    reviewer_notes: Optional[str] = Field(default=None, description="Contextual notes for the Independent Challenger Reviewer")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 9: get_approval_status
# =====================================================================
class GetApprovalStatusArgs(BaseModel):
    """Arguments for get_approval_status tool."""
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(description="Release proposal identifier")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 10: publish_dataset
# =====================================================================
class PublishDatasetArgs(BaseModel):
    """
    Arguments for publish_dataset tool.
    CRITICAL ARCHITECTURE REQUIREMENT:
    AI is strictly prohibited from authorizing publication.
    A valid human approval token cryptographically bound to the artifact hash is mandatory.
    """
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(description="Approved release request identifier")
    approval_token: str = Field(
        min_length=16,
        description="Cryptographic human authorization token issued by authorized Human Steward/Admin",
    )
    expected_artifact_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="Expected SHA-256 hash of the artifact to ensure hash-bound authorization integrity",
    )
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 11: verify_publication
# =====================================================================
class VerifyPublicationArgs(BaseModel):
    """Arguments for verify_publication tool."""
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(description="Executed release identifier to verify")
    destination_target: Optional[str] = Field(default=None, description="Target destination endpoint")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")


# =====================================================================
# Tool 12: withdraw_release
# =====================================================================
class WithdrawReleaseArgs(BaseModel):
    """Arguments for withdraw_release tool."""
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(description="Release request identifier to recall or cancel")
    reason: str = Field(min_length=5, description="Mandatory audit justification for withdrawal")
    organization_id: Optional[str] = Field(default=None, description="Tenant organization workspace UUID")
