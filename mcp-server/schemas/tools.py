"""
Strict Pydantic argument schemas for the 12 frozen ReleaseGate MCP tools.

Every model uses ``extra="forbid"`` and is frozen. The MCP server rejects any
call whose arguments do not validate against the model before it touches a
service method, which prevents parameter injection, type confusion, arbitrary
transformation code, and client-supplied identity or organization overrides.
"""

from __future__ import annotations

import re
from typing import Annotated, Dict, List, Literal, Optional, Union
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)


class StrictArguments(BaseModel):
    """Base class for every MCP tool argument model."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Reusable constrained types
# ---------------------------------------------------------------------------
ColumnName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[^\x00-\x1f/\\]+$",
    ),
]

ReleaseId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^rel_[0-9a-f]{12}$"),
]

ApprovalId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^apr_[0-9a-f]{32}$"),
]

Sha256Hex = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"(?i)^[0-9a-f]{64}$"),
]

PolicyVersion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$"),
]

FilterScalar = Union[StrictStr, StrictInt, StrictFloat, StrictBool]

MaskingStrategyName = Literal[
    "full_redaction",
    "partial_email",
    "partial_phone",
    "last_4_visible",
    "custom_placeholder",
]

GeneralizationStrategyName = Literal[
    "numeric_binning",
    "date_truncation",
    "category_bucketing",
]

def _validate_approved_destination(value: str) -> str:
    """Constrain destinations to approved URI schemes (never local paths)."""
    target = value.strip()
    allowed_schemes = ("s3://", "gcs://", "bigquery://", "sftp://", "internal://")
    if not target.startswith(allowed_schemes):
        raise ValueError(
            "destination_target must use an approved URI scheme: "
            "s3://, gcs://, bigquery://, sftp://, internal://"
        )
    if any(character in target for character in ("\x00", "\r", "\n", "\t", " ")):
        raise ValueError("destination_target must not contain whitespace or control characters")
    if ".." in target.split("/"):
        raise ValueError("destination_target must not contain parent directory segments")
    return target


FilterOperatorName = Literal[
    "equals",
    "not_equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "in_list",
    "not_in_list",
    "is_null",
    "is_not_null",
]


# ===========================================================================
# Transformation operation specifications (Tools 6)
# ===========================================================================
class RemoveColumnOperation(StrictArguments):
    """Drop a non-essential column entirely."""

    operation: Literal["remove_column"] = Field(description="Operation discriminator")
    column: ColumnName = Field(description="Column to remove")


class MaskColumnOperation(StrictArguments):
    """Mask or redact values in a column using an allowlisted strategy."""

    operation: Literal["mask_column"] = Field(description="Operation discriminator")
    column: ColumnName = Field(description="Column to mask")
    strategy: MaskingStrategyName = Field(
        default="full_redaction", description="Allowlisted masking strategy"
    )
    placeholder: str = Field(
        default="[REDACTED]", min_length=1, max_length=32, description="Replacement text"
    )


class PseudonymizeColumnOperation(StrictArguments):
    """Replace values with deterministic server-keyed HMAC-SHA256 tokens."""

    operation: Literal["pseudonymize_column"] = Field(description="Operation discriminator")
    column: ColumnName = Field(description="Column to pseudonymize")
    prefix: str = Field(
        default="PSEUDO_",
        min_length=1,
        max_length=16,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Prefix for generated tokens",
    )


class GeneralizeColumnOperation(StrictArguments):
    """Coarsen numeric ranges, dates, or categories."""

    operation: Literal["generalize_column"] = Field(description="Operation discriminator")
    column: ColumnName = Field(description="Column to generalize")
    strategy: GeneralizationStrategyName = Field(description="Allowlisted generalization strategy")
    bins: Optional[List[StrictFloat]] = Field(
        default=None, min_length=2, max_length=50, description="Strictly increasing numeric bin edges"
    )
    bin_labels: Optional[List[str]] = Field(
        default=None, max_length=49, description="Labels for the numeric bins"
    )
    date_interval: Optional[Literal["YEAR", "MONTH", "DECADE"]] = Field(
        default=None, description="Truncation interval for date truncation"
    )
    category_mapping: Optional[Dict[str, str]] = Field(
        default=None, description="Mapping from raw category to generalized bucket"
    )

    @model_validator(mode="after")
    def validate_strategy_parameters(self) -> "GeneralizeColumnOperation":
        if self.strategy == "numeric_binning":
            if not self.bins:
                raise ValueError("numeric_binning requires 'bins' with at least two edges")
            if any(right <= left for left, right in zip(self.bins, self.bins[1:])):
                raise ValueError("'bins' must be strictly increasing")
            if self.bin_labels is not None and len(self.bin_labels) != len(self.bins) - 1:
                raise ValueError("'bin_labels' length must equal len(bins) - 1")
        if self.strategy == "date_truncation" and self.date_interval is None:
            raise ValueError("date_truncation requires 'date_interval'")
        if self.strategy == "category_bucketing" and not self.category_mapping:
            raise ValueError("category_bucketing requires 'category_mapping'")
        if self.category_mapping is not None and len(self.category_mapping) > 100:
            raise ValueError("'category_mapping' supports at most 100 entries")
        return self


class FilterRowsOperation(StrictArguments):
    """Keep rows that satisfy a declarative, allowlisted comparison."""

    operation: Literal["filter_rows"] = Field(description="Operation discriminator")
    column: ColumnName = Field(description="Column used by the filter")
    operator: FilterOperatorName = Field(description="Allowlisted comparison operator")
    value: Optional[FilterScalar] = Field(default=None, description="Scalar comparison value")
    values_list: Optional[List[FilterScalar]] = Field(
        default=None, max_length=100, description="Value set for in_list / not_in_list"
    )

    @model_validator(mode="after")
    def validate_operator_parameters(self) -> "FilterRowsOperation":
        membership = self.operator in ("in_list", "not_in_list")
        nullary = self.operator in ("is_null", "is_not_null")
        if membership and not self.values_list:
            raise ValueError(f"'{self.operator}' requires 'values_list'")
        if not membership and not nullary and self.value is None:
            raise ValueError(f"'{self.operator}' requires 'value'")
        if membership and self.value is not None:
            raise ValueError(f"'{self.operator}' uses 'values_list', not 'value'")
        return self


TransformationOperationSpec = Annotated[
    Union[
        RemoveColumnOperation,
        MaskColumnOperation,
        PseudonymizeColumnOperation,
        GeneralizeColumnOperation,
        FilterRowsOperation,
    ],
    Field(discriminator="operation"),
]


# ===========================================================================
# Tool 1: inspect_dataset
# ===========================================================================
class InspectDatasetArgs(StrictArguments):
    """Arguments for inspect_dataset."""

    dataset_id: UUID = Field(description="Registered dataset UUID (scope comes from the server session)")
    version_number: StrictInt = Field(default=1, ge=1, le=10000, description="Immutable dataset version")


# ===========================================================================
# Tool 2: detect_sensitive_data
# ===========================================================================
class DetectSensitiveDataArgs(StrictArguments):
    """Arguments for detect_sensitive_data."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    version_number: StrictInt = Field(default=1, ge=1, le=10000, description="Immutable dataset version")
    confidence_threshold: StrictFloat = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum Presidio confidence threshold"
    )
    entities: Optional[List[str]] = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Optional allowlist of Presidio entity types to scan",
    )

    @field_validator("entities")
    @classmethod
    def validate_entities(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized: List[str] = []
        for entity in value:
            cleaned = entity.strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", cleaned):
                raise ValueError(f"Invalid Presidio entity type: {entity!r}")
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized


# ===========================================================================
# Tool 3: validate_data_quality
# ===========================================================================
class ValidateDataQualityArgs(StrictArguments):
    """Arguments for validate_data_quality."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    version_number: StrictInt = Field(default=1, ge=1, le=10000, description="Immutable dataset version")
    allow_nulls: Optional[StrictBool] = Field(
        default=None, description="Override whether null cell values are permitted"
    )
    allow_duplicates: Optional[StrictBool] = Field(
        default=None, description="Override whether duplicate rows are permitted"
    )


# ===========================================================================
# Tool 4: check_release_policy
# ===========================================================================
class CheckReleasePolicyArgs(StrictArguments):
    """Arguments for check_release_policy."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    version_number: StrictInt = Field(default=1, ge=1, le=10000, description="Immutable dataset version")
    policy_version: PolicyVersion = Field(
        default="1.0.0", description="Release policy version to evaluate"
    )
    domain: Optional[str] = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Operational domain tag (e.g. internal_analytics)",
    )


# ===========================================================================
# Tool 5: generate_risk_report
# ===========================================================================
class GenerateRiskReportArgs(StrictArguments):
    """Arguments for generate_risk_report."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    version_number: StrictInt = Field(default=1, ge=1, le=10000, description="Immutable dataset version")
    policy_version: PolicyVersion = Field(
        default="1.0.0", description="Policy version used for scoring"
    )


# ===========================================================================
# Tool 6: propose_transformation
# ===========================================================================
class ProposeTransformationArgs(StrictArguments):
    """Arguments for propose_transformation."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    version_number: StrictInt = Field(default=1, ge=1, le=10000, description="Base dataset version")
    operations: List[TransformationOperationSpec] = Field(
        min_length=1,
        max_length=20,
        description="Ordered list of allowlisted transformation operations",
    )
    rationale: str = Field(
        min_length=5,
        max_length=1000,
        description="Governance justification for the proposed transformation",
    )


# ===========================================================================
# Tool 7: prepare_release
# ===========================================================================
class PrepareReleaseArgs(StrictArguments):
    """Arguments for prepare_release."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    source_version_number: StrictInt = Field(
        default=1, ge=1, le=10000, description="Verified source dataset version"
    )
    destination_target: str = Field(
        min_length=8,
        max_length=512,
        description="Approved destination URI (s3://, gcs://, bigquery://, sftp://, internal://)",
    )
    release_notes: Optional[str] = Field(
        default=None, max_length=1000, description="Release context and notes"
    )

    @field_validator("destination_target")
    @classmethod
    def validate_destination_target(cls, value: str) -> str:
        return _validate_approved_destination(value)


# ===========================================================================
# Tool 8: submit_for_review
# ===========================================================================
class SubmitForReviewArgs(StrictArguments):
    """Arguments for submit_for_review."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    version_number: StrictInt = Field(default=1, ge=1, le=10000, description="Dataset version under review")
    staged_release_id: Optional[ReleaseId] = Field(
        default=None, description="Existing staged release to submit"
    )
    reviewer_notes: Optional[str] = Field(
        default=None, max_length=1000, description="Notes for the Challenger reviewer"
    )


# ===========================================================================
# Tool 9: get_approval_status
# ===========================================================================
class GetApprovalStatusArgs(StrictArguments):
    """Arguments for get_approval_status."""

    release_id: ReleaseId = Field(description="Release identifier")


# ===========================================================================
# Tool 10: publish_dataset
# ===========================================================================
class PublishDatasetArgs(StrictArguments):
    """Arguments for publish_dataset.

    A publication can only proceed with an approval record that a human
    approval channel created outside the MCP surface. The model cannot mint,
    guess, or supply an approval token.
    """

    release_id: ReleaseId = Field(description="Release identifier")
    approval_id: ApprovalId = Field(
        description="Opaque identifier of the human approval record for this exact artifact"
    )
    expected_artifact_hash: Sha256Hex = Field(
        description="SHA-256 hash the caller believes was approved; must match the release"
    )

    @field_validator("expected_artifact_hash")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        return value.strip().lower()


# ===========================================================================
# Tool 11: verify_publication
# ===========================================================================
class VerifyPublicationArgs(StrictArguments):
    """Arguments for verify_publication."""

    release_id: ReleaseId = Field(description="Release identifier")
    destination_target: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=512,
        description="Optional destination override to verify against",
    )

    @field_validator("destination_target")
    @classmethod
    def validate_destination_target(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _validate_approved_destination(value)


# ===========================================================================
# Tool 12: withdraw_release
# ===========================================================================
class WithdrawReleaseArgs(StrictArguments):
    """Arguments for withdraw_release."""

    release_id: ReleaseId = Field(description="Release identifier")
    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Mandatory audit justification for withdrawing the release",
    )


# ---------------------------------------------------------------------------
# Registry used by tests and the server to enumerate the frozen schemas
# ---------------------------------------------------------------------------
TOOL_ARGUMENT_MODELS: Dict[str, type[StrictArguments]] = {
    "inspect_dataset": InspectDatasetArgs,
    "detect_sensitive_data": DetectSensitiveDataArgs,
    "validate_data_quality": ValidateDataQualityArgs,
    "check_release_policy": CheckReleasePolicyArgs,
    "generate_risk_report": GenerateRiskReportArgs,
    "propose_transformation": ProposeTransformationArgs,
    "prepare_release": PrepareReleaseArgs,
    "submit_for_review": SubmitForReviewArgs,
    "get_approval_status": GetApprovalStatusArgs,
    "publish_dataset": PublishDatasetArgs,
    "verify_publication": VerifyPublicationArgs,
    "withdraw_release": WithdrawReleaseArgs,
}

__all__ = [
    "ApprovalId",
    "CheckReleasePolicyArgs",
    "ColumnName",
    "DetectSensitiveDataArgs",
    "FilterOperatorName",
    "FilterRowsOperation",
    "GeneralizationStrategyName",
    "GeneralizeColumnOperation",
    "GenerateRiskReportArgs",
    "GetApprovalStatusArgs",
    "InspectDatasetArgs",
    "MaskColumnOperation",
    "MaskingStrategyName",
    "PrepareReleaseArgs",
    "ProposeTransformationArgs",
    "PseudonymizeColumnOperation",
    "PublishDatasetArgs",
    "ReleaseId",
    "RemoveColumnOperation",
    "Sha256Hex",
    "StrictArguments",
    "SubmitForReviewArgs",
    "TOOL_ARGUMENT_MODELS",
    "TransformationOperationSpec",
    "ValidateDataQualityArgs",
    "VerifyPublicationArgs",
    "WithdrawReleaseArgs",
]
