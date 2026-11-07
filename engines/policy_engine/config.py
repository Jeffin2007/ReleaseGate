"""
Configuration models for the Versioned Release Policy & Risk Engine.
Defines policy rules, scoring weights, forbidden licenses, and threshold parameters.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SensitiveInfoPolicyConfig(BaseModel):
    """Rules for evaluating sensitive information & PII risk (35 points max)."""
    model_config = ConfigDict(frozen=True)

    max_points: float = Field(default=35.0, frozen=True)
    block_on_critical_pii: bool = Field(
        default=True,
        description="Whether detecting CRITICAL severity PII immediately triggers a hard release block"
    )
    block_on_high_pii: bool = Field(
        default=False,
        description="Whether detecting HIGH severity PII triggers a hard release block"
    )
    points_per_high_finding: float = Field(default=12.0)
    points_per_medium_finding: float = Field(default=4.0)
    points_per_low_finding: float = Field(default=1.0)


class DataQualityPolicyConfig(BaseModel):
    """Rules for evaluating dataset quality & integrity risk (20 points max)."""
    model_config = ConfigDict(frozen=True)

    max_points: float = Field(default=20.0, frozen=True)
    min_acceptable_quality_score: float = Field(
        default=85.0,
        description="Minimum acceptable quality score percentage before quality points are penalized"
    )
    block_on_critical_quality_issues: bool = Field(
        default=True,
        description="Whether CRITICAL data quality failures (e.g. missing primary keys) trigger hard blocks"
    )
    points_per_critical_issue: float = Field(default=10.0)
    points_per_high_issue: float = Field(default=5.0)
    points_per_medium_issue: float = Field(default=2.0)


class LicensingProvenancePolicyConfig(BaseModel):
    """Rules for evaluating license compatibility and source provenance (20 points max)."""
    model_config = ConfigDict(frozen=True)

    max_points: float = Field(default=20.0, frozen=True)
    allowed_licenses: List[str] = Field(
        default=[
            "MIT",
            "Apache-2.0",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "CC0-1.0",
            "CC-BY-4.0",
            "OpenData-1.0",
        ],
        description="Approved open/commercial data licenses"
    )
    forbidden_licenses: List[str] = Field(
        default=[
            "GPL-2.0",
            "GPL-3.0",
            "AGPL-3.0",
            "PROPRIETARY_UNLICENSED",
            "NONE",
            "UNKNOWN",
        ],
        description="Prohibited copyleft or unlicensed indicators that pose legal exposure"
    )
    block_on_forbidden_license: bool = Field(
        default=True,
        description="Whether forbidden or unapproved license strings immediately trigger hard blocks"
    )
    require_provenance_source: bool = Field(
        default=True,
        description="Require verifiable origin URL, source system, or collection citation"
    )
    points_for_missing_provenance: float = Field(default=10.0)
    points_for_unapproved_license: float = Field(default=15.0)


class MetadataCompletenessPolicyConfig(BaseModel):
    """Rules for evaluating dataset metadata completeness (10 points max)."""
    model_config = ConfigDict(frozen=True)

    max_points: float = Field(default=10.0, frozen=True)
    required_fields: List[str] = Field(
        default=["dataset_name", "description", "file_format", "file_size", "content_hash"],
        description="Fields that must exist in dataset metadata"
    )
    recommended_fields: List[str] = Field(
        default=["intended_use", "domain", "data_custodian"],
        description="Recommended descriptive metadata fields"
    )
    block_on_missing_required_fields: bool = Field(
        default=True,
        description="Hard block if required baseline metadata fields are missing"
    )
    points_per_missing_required: float = Field(default=3.0)
    points_per_missing_recommended: float = Field(default=1.0)


class PolicyViolationsConfig(BaseModel):
    """Rules for evaluating organizational policy compliance and restricted domains (15 points max)."""
    model_config = ConfigDict(frozen=True)

    max_points: float = Field(default=15.0, frozen=True)
    prohibited_domains: List[str] = Field(
        default=[
            "biometrics_unconsented",
            "classified_defense",
            "underage_surveillance",
            "credit_scoring_unregulated",
        ],
        description="Domain tags strictly forbidden for public or standard AI model release"
    )
    require_retention_policy: bool = Field(
        default=True,
        description="Require explicit data retention schedule specification"
    )
    block_on_prohibited_domain: bool = Field(
        default=True,
        description="Hard block if dataset belongs to a prohibited domain"
    )
    points_for_prohibited_domain: float = Field(default=15.0)
    points_for_missing_retention: float = Field(default=5.0)


class PolicyConfig(BaseModel):
    """
    Versioned Release Policy definition.
    """
    model_config = ConfigDict(frozen=True)

    policy_id: str = Field(default="releasegate-baseline-v1")
    policy_name: str = Field(default="Frozen Architecture Baseline Policy")
    policy_version: str = Field(default="1.0.0")
    description: str = Field(
        default="Standard ReleaseGate v1.0 governance policy for authorizing dataset publication."
    )
    max_acceptable_score: float = Field(
        default=39.99,
        description="Upper score threshold for release eligibility (scores >= 40 are High/Critical risk)"
    )
    sensitive_info: SensitiveInfoPolicyConfig = Field(default_factory=SensitiveInfoPolicyConfig)
    data_quality: DataQualityPolicyConfig = Field(default_factory=DataQualityPolicyConfig)
    licensing_provenance: LicensingProvenancePolicyConfig = Field(default_factory=LicensingProvenancePolicyConfig)
    metadata_completeness: MetadataCompletenessPolicyConfig = Field(default_factory=MetadataCompletenessPolicyConfig)
    policy_violations: PolicyViolationsConfig = Field(default_factory=PolicyViolationsConfig)
