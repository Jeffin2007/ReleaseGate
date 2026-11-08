"""
Pydantic schemas and serialization models for Deterministic Data Quality Validation.
Enforces that validation summaries, rule results, and evidence references contain
aggregate statistics, coordinates, and hashes, while row-level values remain strictly local.
"""

from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class QualitySeverity(str, Enum):
    """Severity tier for a data quality failure."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class RuleType(str, Enum):
    """Categorization of deterministic data quality rules."""
    NOT_NULL = "NOT_NULL"
    UNIQUE = "UNIQUE"
    ALLOWED_VALUES = "ALLOWED_VALUES"
    NUMERIC_RANGE = "NUMERIC_RANGE"
    REGEX_FORMAT = "REGEX_FORMAT"
    DATE_FORMAT = "DATE_FORMAT"
    EXPECTED_DTYPE = "EXPECTED_DTYPE"
    NO_DUPLICATE_ROWS = "NO_DUPLICATE_ROWS"


class EvidenceReference(BaseModel):
    """
    Sanitized statistical and structural evidence for a quality violation.
    Never exposes raw dataset cell values.
    """
    model_config = ConfigDict(frozen=True)

    rule_name: str
    rule_type: RuleType
    column_name: Optional[str] = None
    violating_count: int = Field(ge=0)
    violating_percentage: float = Field(ge=0.0, le=100.0)
    sample_row_indices: List[int] = Field(
        default_factory=list,
        description="Zero-indexed row coordinates of violations (bounded sample for local audit)"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Statistical details (e.g. expected range, observed null count)"
    )
    evidence_hash: str = Field(
        description="Deterministic SHA-256 hash identifying the violation signature"
    )


class QualityIssue(BaseModel):
    """
    Structured quality failure for a specific rule and column.
    """
    model_config = ConfigDict(frozen=True)

    rule_name: str
    rule_type: RuleType
    column_name: Optional[str] = None
    severity: QualitySeverity
    message: str
    violating_count: int = Field(ge=1)
    violating_percentage: float = Field(ge=0.0, le=100.0)
    evidence_ref: EvidenceReference


class QualityRuleResult(BaseModel):
    """
    Evaluation outcome of a single quality rule.
    """
    model_config = ConfigDict(frozen=True)

    rule_name: str
    rule_type: RuleType
    column_name: Optional[str] = None
    passed: bool
    severity: QualitySeverity
    issue: Optional[QualityIssue] = None


class QualitySummary(BaseModel):
    """
    High-level aggregate summary of the quality inspection run.
    """
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    version_number: int
    inspection_run_id: str
    total_rows: int = Field(ge=0)
    total_columns: int = Field(ge=0)
    total_rules_evaluated: int = Field(ge=0)
    passed_rules_count: int = Field(ge=0)
    failed_rules_count: int = Field(ge=0)
    quality_score: float = Field(ge=0.0, le=100.0, description="Percentage of passed rules")
    has_critical_failures: bool = False
    has_high_failures: bool = False
    affected_columns: List[str] = Field(default_factory=list)
    evaluated_at_utc: str


class QualityReport(BaseModel):
    """
    Complete deterministic quality report for a dataset version and inspection run.
    """
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    version_number: int
    inspection_run_id: str
    summary: QualitySummary
    rule_results: List[QualityRuleResult] = Field(default_factory=list)
    issues: List[QualityIssue] = Field(default_factory=list)

    def to_cloud_metadata(self) -> Dict[str, Any]:
        """
        Produce a sanitized, privacy-safe dictionary suitable for outbound transmission
        to the Cloud Control Plane. Guarantees zero raw dataset values are exposed.
        """
        return {
            "dataset_id": self.dataset_id,
            "version_number": self.version_number,
            "inspection_run_id": self.inspection_run_id,
            "summary": self.summary.model_dump(),
            "issues_count": len(self.issues),
            "affected_columns": self.summary.affected_columns,
            "issues": [
                {
                    "rule_name": issue.rule_name,
                    "rule_type": issue.rule_type.value,
                    "column_name": issue.column_name,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "violating_count": issue.violating_count,
                    "violating_percentage": issue.violating_percentage,
                    "evidence_ref": issue.evidence_ref.model_dump(),
                }
                for issue in self.issues
            ],
            "rule_results": [
                {
                    "rule_name": r.rule_name,
                    "rule_type": r.rule_type.value,
                    "column_name": r.column_name,
                    "passed": r.passed,
                    "severity": r.severity.value,
                }
                for r in self.rule_results
            ],
        }


def generate_quality_evidence_hash(
    dataset_id: str,
    version_number: int,
    rule_name: str,
    column_name: Optional[str],
    violating_count: int,
    violating_percentage: float,
) -> str:
    """
    Generate a deterministic SHA-256 fingerprint for a quality violation.
    Does not use raw row values.
    """
    col_str = column_name or "__dataset__"
    signature = f"{dataset_id}:{version_number}:{rule_name}:{col_str}:{violating_count}:{violating_percentage:.4f}"
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()
