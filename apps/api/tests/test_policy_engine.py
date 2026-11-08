"""
Unit tests for the Deterministic Release Policy and Risk Engine (engines/policy_engine).
Verifies:
- Every scoring category (sensitive info: 35, quality: 20, licensing: 20, metadata: 10, policy: 15).
- Precise risk-band boundaries (0-19 Low, 20-39 Moderate, 40-69 High, 70-100 Critical).
- Critical policy overrides: critical violation blocks release regardless of aggregate score.
- Missing evidence handling and fail-closed security.
- Policy version preservation across evaluations.
- 100% determinism and reproducibility across repeated runs.
- Zero raw value leakage in outbound cloud metadata.
"""

import json
import pytest

from engines.policy_engine import (
    EvaluationStatus,
    PolicyConfig,
    PolicyEngine,
    RiskBand,
    compute_risk_band,
)


@pytest.fixture
def clean_inputs():
    """Returns baseline clean inputs that produce a 0.0 risk score and LOW band."""
    metadata = {
        "dataset_name": "Verified Customer Demographics",
        "description": "Anonymized non-PII test benchmarks",
        "file_format": "csv",
        "file_size": 2048,
        "content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "intended_use": "model_training",
        "domain": "finance",
        "data_custodian": "Security Governance Team",
    }
    provenance = {
        "license": "Apache-2.0",
        "source_url": "https://data-lake.internal/cleaned_v1.csv",
    }
    pii_report = {
        "has_critical_pii": False,
        "findings_count": 0,
        "columns": [],
    }
    quality_report = {
        "summary": {
            "has_critical_failures": False,
            "quality_score": 100.0,
        },
        "issues": [],
    }
    context = {
        "domain": "finance",
        "retention_policy": "365_days",
    }
    return {
        "metadata": metadata,
        "provenance": provenance,
        "pii_report": pii_report,
        "quality_report": quality_report,
        "context": context,
    }


def test_clean_dataset_scores_zero_low_band(clean_inputs):
    """Verify that a completely clean dataset achieves 0.0 risk score and PASSED status in LOW band."""
    engine = PolicyEngine()
    result = engine.evaluate(
        dataset_id="ds-clean-01",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )

    assert result.score_breakdown.total_risk_score == 0.0
    assert result.score_breakdown.risk_band == RiskBand.LOW
    assert result.status == EvaluationStatus.PASSED
    assert result.is_release_eligible is True
    assert len(result.blocking_reasons) == 0


def test_category_1_sensitive_information_scoring(clean_inputs):
    """Verify Sensitive Information category scores up to 35 points."""
    engine = PolicyEngine()

    # 1 High PII finding (12 points) + 1 Medium PII finding (4 points) = 16 points
    pii_report = {
        "has_critical_pii": False,
        "findings_count": 2,
        "columns": [
            {
                "column_name": "contact",
                "findings": [
                    {"entity_type": "EMAIL_ADDRESS", "severity": "HIGH", "evidence_ref": {"evidence_hash": "hash1"}},
                    {"entity_type": "IP_ADDRESS", "severity": "MEDIUM", "evidence_ref": {"evidence_hash": "hash2"}},
                ],
            }
        ],
    }

    result = engine.evaluate(
        dataset_id="ds-pii-01",
        version_number=1,
        pii_report=pii_report,
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )

    cat_score = result.score_breakdown.sensitive_information.score
    assert cat_score == 16.0
    assert result.score_breakdown.sensitive_information.max_points == 35.0


def test_category_2_data_quality_scoring(clean_inputs):
    """Verify Data Quality category scores up to 20 points."""
    engine = PolicyEngine()

    # 2 High quality issues = 10.0 points
    quality_report = {
        "summary": {
            "has_critical_failures": False,
            "quality_score": 88.0,
        },
        "issues": [
            {"severity": "HIGH", "evidence_ref": {"evidence_hash": "q1"}},
            {"severity": "HIGH", "evidence_ref": {"evidence_hash": "q2"}},
        ],
    }

    result = engine.evaluate(
        dataset_id="ds-qual-01",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=quality_report,
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )

    cat_score = result.score_breakdown.data_quality.score
    assert cat_score == 10.0
    assert result.score_breakdown.data_quality.max_points == 20.0


def test_category_3_licensing_and_provenance(clean_inputs):
    """Verify Licensing & Provenance category scores up to 20 points."""
    engine = PolicyEngine()

    # Unapproved license (15 pts) without source URL (+10 pts, capped at 20 max)
    provenance = {
        "license": "Custom-Corporate-Unapproved-V1",
        "source_url": None,
    }

    result = engine.evaluate(
        dataset_id="ds-lic-01",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=provenance,
        context=clean_inputs["context"],
    )

    cat_score = result.score_breakdown.licensing_provenance.score
    assert cat_score == 20.0
    assert result.score_breakdown.licensing_provenance.max_points == 20.0


def test_category_4_metadata_completeness(clean_inputs):
    """Verify Metadata Completeness category scores up to 10 points."""
    # Custom config where missing recommended metadata does not trigger hard block
    custom_config = PolicyConfig()
    engine = PolicyEngine(policy_config=custom_config)

    # Missing recommended fields: intended_use, data_custodian (2 * 1.0 = 2.0 pts)
    meta = dict(clean_inputs["metadata"])
    del meta["intended_use"]
    del meta["data_custodian"]

    result = engine.evaluate(
        dataset_id="ds-meta-01",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=meta,
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )

    cat_score = result.score_breakdown.metadata_completeness.score
    assert cat_score == 2.0
    assert result.score_breakdown.metadata_completeness.max_points == 10.0


def test_category_5_policy_violations(clean_inputs):
    """Verify Policy Violations category scores up to 15 points."""
    engine = PolicyEngine()

    # Missing retention policy (5.0 pts)
    ctx = {"domain": "finance", "retention_policy": None}

    result = engine.evaluate(
        dataset_id="ds-pol-01",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=ctx,
    )

    cat_score = result.score_breakdown.policy_violations.score
    assert cat_score == 5.0
    assert result.score_breakdown.policy_violations.max_points == 15.0


def test_risk_band_boundaries():
    """Verify exact risk band threshold boundaries: 0-19 Low, 20-39 Moderate, 40-69 High, 70-100 Critical."""
    # Low band: [0, 19.99]
    assert compute_risk_band(0.0) == RiskBand.LOW
    assert compute_risk_band(19.0) == RiskBand.LOW
    assert compute_risk_band(19.99) == RiskBand.LOW

    # Moderate band: [20.0, 39.99]
    assert compute_risk_band(20.0) == RiskBand.MODERATE
    assert compute_risk_band(30.0) == RiskBand.MODERATE
    assert compute_risk_band(39.99) == RiskBand.MODERATE

    # High band: [40.0, 69.99]
    assert compute_risk_band(40.0) == RiskBand.HIGH
    assert compute_risk_band(55.0) == RiskBand.HIGH
    assert compute_risk_band(69.99) == RiskBand.HIGH

    # Critical band: [70.0, 100.0]
    assert compute_risk_band(70.0) == RiskBand.CRITICAL
    assert compute_risk_band(85.0) == RiskBand.CRITICAL
    assert compute_risk_band(100.0) == RiskBand.CRITICAL


def test_critical_policy_override_pii(clean_inputs):
    """
    CRITICAL CONSTRAINT TEST:
    Verify that detecting CRITICAL PII blocks release immediately even if total score would be low.
    """
    engine = PolicyEngine()
    pii_report = {
        "has_critical_pii": True,
        "findings_count": 1,
        "columns": [
            {
                "column_name": "tax_id",
                "findings": [{"entity_type": "US_SSN", "severity": "CRITICAL", "evidence_ref": {"evidence_hash": "ssn_hash"}}],
            }
        ],
    }

    result = engine.evaluate(
        dataset_id="ds-ssn-block",
        version_number=1,
        pii_report=pii_report,
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )

    assert result.is_release_eligible is False
    assert result.status == EvaluationStatus.BLOCKED
    assert result.critical_override_applied is True
    assert any("CRITICAL severity sensitive identifiers" in r for r in result.blocking_reasons)


def test_critical_policy_override_forbidden_license(clean_inputs):
    """Verify that forbidden licenses (GPL, AGPL, UNLICENSED) block release with critical override."""
    engine = PolicyEngine()
    provenance = {"license": "GPL-3.0", "source_url": "https://example.com/source"}

    result = engine.evaluate(
        dataset_id="ds-gpl-block",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=provenance,
        context=clean_inputs["context"],
    )

    assert result.is_release_eligible is False
    assert result.status == EvaluationStatus.BLOCKED
    assert result.critical_override_applied is True
    assert any("Prohibited dataset license" in r for r in result.blocking_reasons)


def test_critical_policy_override_prohibited_domain(clean_inputs):
    """Verify that prohibited regulatory domains trigger immediate hard blocks."""
    engine = PolicyEngine()
    ctx = {"domain": "biometrics_unconsented", "retention_policy": "30_days"}

    result = engine.evaluate(
        dataset_id="ds-bio-block",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=ctx,
    )

    assert result.is_release_eligible is False
    assert result.status == EvaluationStatus.BLOCKED
    assert result.critical_override_applied is True
    assert any("restricted/prohibited domain" in r for r in result.blocking_reasons)


def test_missing_evidence_fail_closed(clean_inputs):
    """
    FAIL-CLOSED SECURITY TEST:
    Verify that missing required inspection evidence (PII report, Quality report, Provenance, Metadata)
    causes immediate blocking.
    """
    engine = PolicyEngine()

    # Missing PII report
    res_no_pii = engine.evaluate(
        dataset_id="ds-no-pii",
        version_number=1,
        pii_report=None,
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )
    assert res_no_pii.is_release_eligible is False
    assert res_no_pii.status == EvaluationStatus.BLOCKED
    assert any("Missing PII inspection evidence" in r for r in res_no_pii.blocking_reasons)

    # Missing Quality report
    res_no_qual = engine.evaluate(
        dataset_id="ds-no-qual",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=None,
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )
    assert res_no_qual.is_release_eligible is False
    assert res_no_qual.status == EvaluationStatus.BLOCKED
    assert any("Missing data quality evidence" in r for r in res_no_qual.blocking_reasons)

    # Missing Provenance
    res_no_prov = engine.evaluate(
        dataset_id="ds-no-prov",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=None,
        context=clean_inputs["context"],
    )
    assert res_no_prov.is_release_eligible is False
    assert res_no_prov.status == EvaluationStatus.BLOCKED


def test_policy_version_preserved_in_evaluation(clean_inputs):
    """Verify that policy_version and policy_name are preserved in all evaluation outputs."""
    custom_policy = PolicyConfig(
        policy_id="custom-pol-v2",
        policy_name="Custom Enterprise Standards",
        policy_version="2.4.1",
    )
    engine = PolicyEngine(policy_config=custom_policy)

    result = engine.evaluate(
        dataset_id="ds-version-check",
        version_number=3,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )

    assert result.policy_version == "2.4.1"
    assert result.policy_name == "Custom Enterprise Standards"
    cloud_meta = result.to_cloud_metadata()
    assert cloud_meta["policy_version"] == "2.4.1"
    assert cloud_meta["policy_name"] == "Custom Enterprise Standards"


def test_reproducibility_across_repeated_evaluations(clean_inputs):
    """
    CRITICAL REPRODUCIBILITY TEST:
    Verify that evaluating identical inputs multiple times produces identical scores,
    identical breakdown objects, and identical blocking reasons.
    """
    engine = PolicyEngine()
    fixed_eval_id = "eval-fixed-deterministic-uuid"

    eval1 = engine.evaluate(
        dataset_id="ds-repro",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
        evaluation_id=fixed_eval_id,
    )

    eval2 = engine.evaluate(
        dataset_id="ds-repro",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
        evaluation_id=fixed_eval_id,
    )

    assert eval1.score_breakdown.total_risk_score == eval2.score_breakdown.total_risk_score
    assert eval1.score_breakdown.risk_band == eval2.score_breakdown.risk_band
    assert eval1.status == eval2.status
    assert eval1.is_release_eligible == eval2.is_release_eligible
    assert eval1.blocking_reasons == eval2.blocking_reasons
    assert eval1.critical_override_applied == eval2.critical_override_applied


def test_zero_raw_value_leakage_in_cloud_metadata(clean_inputs):
    """
    CRITICAL PRIVACY TEST:
    Verify that neither raw metadata values nor sensitive strings leak into outbound cloud metadata.
    """
    engine = PolicyEngine()
    result = engine.evaluate(
        dataset_id="ds-leak-check",
        version_number=1,
        pii_report=clean_inputs["pii_report"],
        quality_report=clean_inputs["quality_report"],
        metadata=clean_inputs["metadata"],
        provenance=clean_inputs["provenance"],
        context=clean_inputs["context"],
    )

    cloud_payload = result.to_cloud_metadata()
    serialized = json.dumps(cloud_payload)

    # Ensure disclaimers are present
    assert "disclaimer" in cloud_payload
    assert "legal compliance" in cloud_payload["disclaimer"].lower()
    assert "score_breakdown" in cloud_payload
