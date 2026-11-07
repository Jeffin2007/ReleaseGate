"""
Configuration models for Deterministic Data Quality Validation.
Supports configurable dataset-level and column-level rules.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field

from .schemas import QualitySeverity


class DatasetLevelRules(BaseModel):
    """
    Validation rules that apply to the entire dataset.
    """
    no_duplicate_rows: bool = Field(
        default=True,
        description="Fail if identical duplicate rows exist in the dataset"
    )
    max_total_null_percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Upper threshold for aggregate null percentage across the dataset"
    )
    required_columns: Optional[List[str]] = Field(
        default=None,
        description="List of column names that must exist in the dataset schema"
    )
    duplicate_rows_severity: QualitySeverity = Field(
        default=QualitySeverity.HIGH,
        description="Severity assigned when duplicate rows are found"
    )


class ColumnRule(BaseModel):
    """
    Validation constraints for an individual dataset column.
    """
    column_name: str = Field(description="Name of the target column to validate")
    allow_null: bool = Field(
        default=True,
        description="Whether null/missing values are permitted in this column"
    )
    max_null_percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Maximum permitted null percentage (e.g. 5.0 for 5%)"
    )
    unique: bool = Field(
        default=False,
        description="Whether values in this column must be strictly unique (no duplicates)"
    )
    allowed_values: Optional[List[Any]] = Field(
        default=None,
        description="Explicit enumeration of permitted values (e.g. ['PENDING', 'APPROVED', 'REJECTED'])"
    )
    min_value: Optional[float] = Field(
        default=None,
        description="Minimum allowed numeric value (inclusive)"
    )
    max_value: Optional[float] = Field(
        default=None,
        description="Maximum allowed numeric value (inclusive)"
    )
    regex_pattern: Optional[str] = Field(
        default=None,
        description="Regular expression string format requirement (e.g. r'^[A-Z]{3}-\\d{4}$')"
    )
    date_format: Optional[str] = Field(
        default=None,
        description="Expected datetime format string (e.g. '%Y-%m-%d') or 'ISO8601'"
    )
    expected_dtype: Optional[str] = Field(
        default=None,
        description="Normalized semantic type: 'integer', 'float', 'string', 'boolean', 'datetime'"
    )
    severity: QualitySeverity = Field(
        default=QualitySeverity.HIGH,
        description="Severity level if this column rule fails"
    )


class QualityValidationConfig(BaseModel):
    """
    Top-level configuration for deterministic quality validation.
    """
    dataset_rules: DatasetLevelRules = Field(
        default_factory=DatasetLevelRules,
        description="Global dataset-level checks"
    )
    column_rules: List[ColumnRule] = Field(
        default_factory=list,
        description="List of column-specific validation rules"
    )
    sample_row_limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of violating row indices to capture in local evidence reference"
    )
