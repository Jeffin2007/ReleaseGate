"""
Configuration models for the Local Privacy & PII Detection Engine.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .schemas import PIISeverity


class CustomPatternRecognizerConfig(BaseModel):
    """
    Configuration for adding a custom deterministic pattern recognizer to Presidio.
    Allows organizations to scan for internal identifiers, employee numbers,
    project codes, or regional identifiers.
    """
    name: str = Field(description="Unique identifier for the recognizer")
    supported_entity: str = Field(description="Entity label, e.g. EMPLOYEE_ID, API_KEY_TOKEN")
    patterns: List[Dict[str, Any]] = Field(
        description="List of pattern dictionaries containing 'name', 'regex', and 'score'"
    )
    context: Optional[List[str]] = Field(
        default=None,
        description="Optional contextual words that boost confidence if found nearby"
    )
    supported_language: str = Field(default="en", description="Language code for the recognizer")
    severity: PIISeverity = Field(
        default=PIISeverity.HIGH,
        description="Assigned severity level for this custom entity type"
    )


class PIIDetectorConfig(BaseModel):
    """
    Primary configuration for the PII detection engine.
    """
    language: str = Field(default="en", description="ISO 639-1 language code")
    supported_entities: Optional[List[str]] = Field(
        default=None,
        description="Filter to specific entity types. If None, all configured recognizers run."
    )
    confidence_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum Presidio score required to register a detection."
    )
    max_rows_to_sample: Optional[int] = Field(
        default=None,
        description="Optional upper bound on rows scanned per column. None scans entire dataset."
    )
    severity_overrides: Dict[str, PIISeverity] = Field(
        default_factory=dict,
        description="Custom mappings to override default entity severity levels."
    )
    custom_recognizers: List[CustomPatternRecognizerConfig] = Field(
        default_factory=list,
        description="Custom deterministic pattern recognizers to register."
    )
    spacy_model_name: str = Field(
        default="en_core_web_sm",
        description="spaCy model name for English NER."
    )
    allow_nlp_fallback: bool = Field(
        default=True,
        description="If True, gracefully falls back to pattern-only scanning when NLP models are unavailable."
    )
