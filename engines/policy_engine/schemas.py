"""
Pydantic schemas and serialization models for the Deterministic Release Policy & Risk Engine.
Defines risk score breakdowns, risk bands, evaluation status, and evidence references.
"""

from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RiskBand(str, Enum):
    """
    Standard risk bands specified by Frozen Architecture Baseline v1.0.
    - 0-19: Low
    - 20-39: Moderate
    - 40-69: High
    - 70-100: Critical
    """
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvaluationStatus(str, Enum):
    """Decision status of the release policy evaluation."""
    PASSED = "PASSED"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class CategoryScore(BaseModel):
    """
    Score contribution of an individual risk evaluation category.
    """
    model_config = ConfigDict(frozen=True)

    category_name: str
    max_points: float = Field(ge=0.0, le=100.0)
    score: float = Field(ge=0.0, le=100.0)
    risk_weight_percentage: float = Field(ge=0.0, le=100.0)
    passed: bool
    is_critical_violation: bool = False
    findings_summary: str
    evidence_references: List[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    """
    Frozen weighted risk score breakdown (Total = 100 points):
    1. Sensitive information: 35 points
    2. Data quality: 20 points
    3. Licensing and provenance: 20 points
    4. Metadata completeness: 10 points
    5. Policy violations: 15 points
    """
    model_config = ConfigDict(frozen=True)

    sensitive_information: CategoryScore
    data_quality: CategoryScore
    licensing_provenance: CategoryScore
    metadata_completeness: CategoryScore
    policy_violations: CategoryScore
    total_risk_score: float = Field(ge=0.0, le=100.0)
    risk_band: RiskBand


class PolicyEvaluationResult(BaseModel):
    """
    Comprehensive, deterministic result of evaluating a dataset against a versioned release policy.
    """
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    version_number: int
    policy_name: str
    policy_version: str
    evaluated_at_utc: str
    evaluation_id: str
    is_release_eligible: bool
    status: EvaluationStatus
    score_breakdown: ScoreBreakdown
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    evidence_references: List[Dict[str, Any]] = Field(default_factory=list)
    critical_override_applied: bool = False
    disclaimer: str = (
        "Deterministic risk score and release policy evaluation. This score reflects internal organizational "
        "governance thresholds and does not constitute a legal compliance guarantee or regulatory certification."
    )

    def to_cloud_metadata(self) -> Dict[str, Any]:
        """
        Produce a sanitized metadata payload suitable for outbound synchronization to the Cloud Control Plane.
        Contains ZERO raw dataset values.
        """
        return {
            "dataset_id": self.dataset_id,
            "version_number": self.version_number,
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "evaluation_id": self.evaluation_id,
            "evaluated_at_utc": self.evaluated_at_utc,
            "is_release_eligible": self.is_release_eligible,
            "status": self.status.value,
            "total_risk_score": self.score_breakdown.total_risk_score,
            "risk_band": self.score_breakdown.risk_band.value,
            "critical_override_applied": self.critical_override_applied,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
            "score_breakdown": {
                "sensitive_information": self.score_breakdown.sensitive_information.model_dump(),
                "data_quality": self.score_breakdown.data_quality.model_dump(),
                "licensing_provenance": self.score_breakdown.licensing_provenance.model_dump(),
                "metadata_completeness": self.score_breakdown.metadata_completeness.model_dump(),
                "policy_violations": self.score_breakdown.policy_violations.model_dump(),
            },
            "evidence_references_count": len(self.evidence_references),
            "disclaimer": self.disclaimer,
        }


def compute_risk_band(score: float) -> RiskBand:
    """
    Deterministic risk-band mapping according to Frozen Architecture Baseline v1.0:
    - 0-19: Low
    - 20-39: Moderate
    - 40-69: High
    - 70-100: Critical
    """
    if score < 20.0:
        return RiskBand.LOW
    elif score < 40.0:
        return RiskBand.MODERATE
    elif score < 70.0:
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def generate_policy_evidence_hash(
    dataset_id: str,
    version_number: int,
    policy_version: str,
    total_score: float,
    status: str,
    blocking_count: int,
) -> str:
    """
    Generate a deterministic SHA-256 fingerprint for a policy evaluation outcome.
    """
    signature = f"{dataset_id}:{version_number}:{policy_version}:{total_score:.2f}:{status}:{blocking_count}"
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()
