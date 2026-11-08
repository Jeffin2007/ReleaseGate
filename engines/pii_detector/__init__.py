"""
Local Privacy and PII Detection Engine.
Deterministic local scanning based on Microsoft Presidio Analyzer.
"""

from .config import CustomPatternRecognizerConfig, PIIDetectorConfig
from .detector import PIIDetector
from .exceptions import (
    InvalidDatasetError,
    LanguageModelUnavailableError,
    PIIDetectionError,
    UnsupportedLanguageError,
)
from .schemas import (
    DEFAULT_SEVERITY_MAPPING,
    ColumnPIISummary,
    EvidenceReference,
    PIIDetectionMetadata,
    PIIDetectionReport,
    PIIFinding,
    PIISeverity,
    generate_evidence_hash,
)

__all__ = [
    "PIIDetector",
    "PIIDetectorConfig",
    "CustomPatternRecognizerConfig",
    "PIISeverity",
    "PIIFinding",
    "ColumnPIISummary",
    "PIIDetectionReport",
    "PIIDetectionMetadata",
    "EvidenceReference",
    "generate_evidence_hash",
    "DEFAULT_SEVERITY_MAPPING",
    "PIIDetectionError",
    "LanguageModelUnavailableError",
    "UnsupportedLanguageError",
    "InvalidDatasetError",
]
