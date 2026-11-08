"""
Pydantic schemas and serialization models for the Safe Dataset Transformation Engine.
Enforces strictly typed declarative operations and rejects arbitrary executable code expressions.
"""

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class OperationType(str, Enum):
    """Allowlisted declarative transformation operations."""
    REMOVE_COLUMN = "REMOVE_COLUMN"
    MASK_COLUMN = "MASK_COLUMN"
    PSEUDONYMIZE_COLUMN = "PSEUDONYMIZE_COLUMN"
    GENERALIZE_COLUMN = "GENERALIZE_COLUMN"
    FILTER_ROWS = "FILTER_ROWS"


class MaskingStrategy(str, Enum):
    """Standardized masking strategies."""
    FULL_REDACTION = "FULL_REDACTION"       # e.g. "[REDACTED]"
    PARTIAL_EMAIL = "PARTIAL_EMAIL"         # e.g. "j***e@domain.com"
    PARTIAL_PHONE = "PARTIAL_PHONE"         # e.g. "***-***-0199"
    LAST_4_VISIBLE = "LAST_4_VISIBLE"       # e.g. "***-**-1234"
    CUSTOM_PLACEHOLDER = "CUSTOM_PLACEHOLDER"


class GeneralizationStrategy(str, Enum):
    """Controlled data generalization techniques."""
    NUMERIC_BINNING = "NUMERIC_BINNING"       # e.g. [0, 18, 35, 65, 120] -> "18-34"
    DATE_TRUNCATION = "DATE_TRUNCATION"       # Truncate to YEAR or MONTH
    CATEGORY_BUCKETING = "CATEGORY_BUCKETING" # Map granular classes to higher-order buckets


class FilterOperator(str, Enum):
    """Allowlisted comparison operators for row filtering (no eval or SQL allowed)."""
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    IN_LIST = "IN_LIST"
    NOT_IN_LIST = "NOT_IN_LIST"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"


class RemoveColumnOp(BaseModel):
    """Declarative operation to drop one or more columns."""
    model_config = ConfigDict(frozen=True)

    op_type: Literal[OperationType.REMOVE_COLUMN] = OperationType.REMOVE_COLUMN
    column_name: str = Field(description="Name of the column to remove")


class MaskColumnOp(BaseModel):
    """Declarative operation to mask or redact column content."""
    model_config = ConfigDict(frozen=True)

    op_type: Literal[OperationType.MASK_COLUMN] = OperationType.MASK_COLUMN
    column_name: str = Field(description="Name of the column to mask")
    strategy: MaskingStrategy = Field(default=MaskingStrategy.FULL_REDACTION)
    placeholder: str = Field(default="[REDACTED]", description="Text to replace masked content")


class PseudonymizeColumnOp(BaseModel):
    """Declarative operation for deterministic keyed HMAC-SHA256 pseudonymization."""
    model_config = ConfigDict(frozen=True)

    op_type: Literal[OperationType.PSEUDONYMIZE_COLUMN] = OperationType.PSEUDONYMIZE_COLUMN
    column_name: str = Field(description="Name of the column to pseudonymize")
    salt: Optional[str] = Field(default=None, description="Optional per-column salt override")
    prefix: str = Field(default="PSEUDO_", description="Prefix prepended to generated pseudonym token")


class GeneralizeColumnOp(BaseModel):
    """Declarative operation to coarsen numeric ranges, dates, or categories."""
    model_config = ConfigDict(frozen=True)

    op_type: Literal[OperationType.GENERALIZE_COLUMN] = OperationType.GENERALIZE_COLUMN
    column_name: str = Field(description="Name of the column to generalize")
    strategy: GeneralizationStrategy
    bins: Optional[List[float]] = Field(
        default=None,
        description="Numeric bin boundaries (e.g. [0, 18, 30, 50, 65, 120])"
    )
    bin_labels: Optional[List[str]] = Field(
        default=None,
        description="Labels for numeric bins (e.g. ['<18', '18-29', '30-49', '50-64', '65+'])"
    )
    date_interval: Optional[Literal["YEAR", "MONTH", "DECADE"]] = Field(
        default=None,
        description="Truncation interval for dates"
    )
    category_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        description="Mapping from raw category to generalized bucket"
    )


class FilterRowsOp(BaseModel):
    """Declarative row filtering operation (keeps rows satisfying the condition)."""
    model_config = ConfigDict(frozen=True)

    op_type: Literal[OperationType.FILTER_ROWS] = OperationType.FILTER_ROWS
    column_name: str = Field(description="Target column for the filter condition")
    operator: FilterOperator = Field(description="Allowlisted comparison operator")
    value: Optional[Any] = Field(default=None, description="Scalar comparison value")
    values_list: Optional[List[Any]] = Field(
        default=None,
        description="Set of values when using IN_LIST or NOT_IN_LIST"
    )


# Discriminated union of allowlisted operations
TransformationOperation = Annotated[
    Union[
        RemoveColumnOp,
        MaskColumnOp,
        PseudonymizeColumnOp,
        GeneralizeColumnOp,
        FilterRowsOp,
    ],
    Field(discriminator="op_type"),
]


class TransformationSpec(BaseModel):
    """
    Structured specification of one or more transformations to execute sequentially.
    """
    model_config = ConfigDict(frozen=True)

    spec_id: str = Field(default="default-transform-spec")
    description: Optional[str] = None
    operations: List[TransformationOperation] = Field(
        default_factory=list,
        description="Ordered sequence of transformations to execute"
    )
    global_salt: Optional[str] = Field(
        default=None,
        description="Shared salt secret for deterministic pseudonymization"
    )


class OperationSummary(BaseModel):
    """Statistical summary of a single transformation operation execution."""
    model_config = ConfigDict(frozen=True)

    op_type: OperationType
    target_column: str
    affected_count: int
    details: Dict[str, Any] = Field(default_factory=dict)


class TransformationPreview(BaseModel):
    """
    Aggregate summary of transformation changes without exposing sensitive row values.
    """
    model_config = ConfigDict(frozen=True)

    input_row_count: int
    output_row_count: int
    rows_removed: int
    input_column_count: int
    output_column_count: int
    columns_removed: List[str]
    columns_modified: List[str]
    operation_summaries: List[OperationSummary]


class TransformationProvenance(BaseModel):
    """
    Cryptographic lineage and execution record for a dataset transformation.
    """
    model_config = ConfigDict(frozen=True)

    transformation_id: str
    dataset_id: str
    input_version: int
    output_version: int
    input_hash: str
    output_hash: str
    applied_operations: List[Dict[str, Any]]
    transformed_at_utc: str
    input_artifact_ref: Optional[str] = None
    output_artifact_ref: Optional[str] = None


class TransformationResult(BaseModel):
    """
    Comprehensive result of a dataset transformation including provenance, preview,
    and optional re-evaluated verification reports.
    """
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    input_version: int
    output_version: int
    input_hash: str
    output_hash: str
    provenance: TransformationProvenance
    preview: TransformationPreview
    output_artifact_ref: Optional[str] = None
    post_pii_report: Optional[Dict[str, Any]] = None
    post_quality_report: Optional[Dict[str, Any]] = None
    post_policy_evaluation: Optional[Dict[str, Any]] = None
    disclaimer: str = (
        "Controlled transformations reduce identified release risks but do not automatically "
        "guarantee dataset safety or compliance. Post-transformation verification must always be reviewed."
    )

    def to_cloud_metadata(self) -> Dict[str, Any]:
        """
        Export a sanitized metadata payload suitable for the Cloud Control Plane.
        Contains zero raw dataset values.
        """
        return {
            "dataset_id": self.dataset_id,
            "input_version": self.input_version,
            "output_version": self.output_version,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "output_artifact_ref": self.output_artifact_ref,
            "provenance": self.provenance.model_dump(),
            "preview": self.preview.model_dump(),
            "has_post_verification": (
                self.post_pii_report is not None
                and self.post_quality_report is not None
                and self.post_policy_evaluation is not None
            ),
            "post_policy_status": (
                self.post_policy_evaluation.get("status")
                if self.post_policy_evaluation
                else None
            ),
            "disclaimer": self.disclaimer,
        }
