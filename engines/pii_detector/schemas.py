"""
Pydantic schemas and serialization models for the Local Privacy & PII Detection Engine.
Enforces strict boundaries: findings contain statistics, distributions, and hashes,
with absolute guarantee that no raw text or sensitive substring is ever included.
"""

from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PIISeverity(str, Enum):
    """Categorized severity level for detected PII entities."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


DEFAULT_SEVERITY_MAPPING: Dict[str, PIISeverity] = {
    # High-impact identity and financial credentials
    "US_SSN": PIISeverity.CRITICAL,
    "CREDIT_CARD": PIISeverity.CRITICAL,
    "US_PASSPORT": PIISeverity.CRITICAL,
    "UK_NHS": PIISeverity.CRITICAL,
    "MEDICAL_LICENSE": PIISeverity.CRITICAL,
    # Direct identifiers and financial accounts
    "PERSON": PIISeverity.HIGH,
    "EMAIL_ADDRESS": PIISeverity.HIGH,
    "PHONE_NUMBER": PIISeverity.HIGH,
    "US_DRIVER_LICENSE": PIISeverity.HIGH,
    "US_BANK_NUMBER": PIISeverity.HIGH,
    "IBAN_CODE": PIISeverity.HIGH,
    "CRYPTO": PIISeverity.HIGH,
    # Quasi-identifiers and network coordinates
    "LOCATION": PIISeverity.MEDIUM,
    "IP_ADDRESS": PIISeverity.MEDIUM,
    # Low-risk or informational indicators
    "DATE_TIME": PIISeverity.LOW,
    "URL": PIISeverity.LOW,
    "NRP": PIISeverity.LOW,
}


class EvidenceReference(BaseModel):
    """
    Sanitized statistical and structural evidence for a PII finding.
    Provides verifiable proof and debugging coordinates without exposing raw text.
    """
    model_config = ConfigDict(frozen=True)

    column_name: str = Field(description="Name of the scanned column")
    entity_type: str = Field(description="Detected PII entity type")
    matched_count: int = Field(ge=1, description="Number of occurrences detected")
    min_score: float = Field(ge=0.0, le=1.0, description="Minimum confidence score")
    max_score: float = Field(ge=0.0, le=1.0, description="Maximum confidence score")
    avg_score: float = Field(ge=0.0, le=1.0, description="Average confidence score")
    sample_row_indices: List[int] = Field(
        default_factory=list,
        description="Zero-indexed row coordinates of detections (bounded sample for audit)",
    )
    length_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of detected token character lengths",
    )
    evidence_hash: str = Field(
        description="Deterministic SHA-256 hash identifying the detection signature",
    )


class PIIFinding(BaseModel):
    """
    Structured PII finding for a specific entity type within a column.
    """
    model_config = ConfigDict(frozen=True)

    column_name: str
    entity_type: str
    occurrence_count: int = Field(ge=1)
    severity: PIISeverity
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ref: EvidenceReference

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ColumnPIISummary(BaseModel):
    """
    Summary of privacy and PII findings for a single dataset column.
    """
    model_config = ConfigDict(frozen=True)

    column_name: str
    total_scanned_rows: int = Field(ge=0)
    pii_detected: bool
    findings: List[PIIFinding] = Field(default_factory=list)
    highest_severity: Optional[PIISeverity] = None


class PIIDetectionMetadata(BaseModel):
    """
    Sanitized scan-level metadata and configuration summary.
    """
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    version_number: int
    total_rows_scanned: int
    total_columns_scanned: int
    total_findings_count: int
    scanned_at_utc: str
    nlp_engine: str
    language: str = "en"
    disclaimer: str = (
        "Deterministic automated scan based on pattern matching and local NLP. "
        "Does not guarantee complete detection of all sensitive information or regulatory compliance."
    )


class PIIDetectionReport(BaseModel):
    """
    Complete privacy detection report for a dataset version.
    Designed for local evaluation and safe outbound cloud metadata synchronization.
    """
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    version_number: int
    summary: PIIDetectionMetadata
    columns: List[ColumnPIISummary] = Field(default_factory=list)
    findings: List[PIIFinding] = Field(default_factory=list)
    has_critical_pii: bool = False
    has_high_pii: bool = False

    def to_cloud_metadata(self) -> Dict[str, Any]:
        """
        Produce a sanitized, privacy-safe dictionary suitable for outbound transmission
        to the Cloud Control Plane.
        Enforces that zero raw dataset content or unredacted sensitive values are present.
        """
        payload = {
            "dataset_id": self.dataset_id,
            "version_number": self.version_number,
            "summary": self.summary.model_dump(),
            "has_critical_pii": self.has_critical_pii,
            "has_high_pii": self.has_high_pii,
            "findings_count": len(self.findings),
            "columns": [
                {
                    "column_name": col.column_name,
                    "total_scanned_rows": col.total_scanned_rows,
                    "pii_detected": col.pii_detected,
                    "highest_severity": col.highest_severity.value if col.highest_severity else None,
                    "findings": [
                        {
                            "column_name": f.column_name,
                            "entity_type": f.entity_type,
                            "occurrence_count": f.occurrence_count,
                            "severity": f.severity.value,
                            "confidence": f.confidence,
                            "evidence_ref": f.evidence_ref.model_dump(),
                        }
                        for f in col.findings
                    ],
                }
                for col in self.columns
            ],
        }
        return payload


def generate_evidence_hash(
    dataset_id: str,
    version_number: int,
    column_name: str,
    entity_type: str,
    occurrence_count: int,
    min_score: float,
    max_score: float,
) -> str:
    """
    Generate a deterministic SHA-256 fingerprint for a PII evidence reference
    without including raw text.
    """
    content = f"{dataset_id}:{version_number}:{column_name}:{entity_type}:{occurrence_count}:{min_score:.4f}:{max_score:.4f}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
