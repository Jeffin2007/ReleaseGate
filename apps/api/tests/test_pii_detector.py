"""
Unit tests for the Local Privacy & PII Detection Engine (engines/pii_detector).
Verifies:
- Detection of core PII entities: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, IP_ADDRESS, CREDIT_CARD, US_SSN.
- Multiple sensitive entities in a single column.
- Empty columns and all-null series.
- Non-PII clean columns.
- Strict isolation and zero raw sensitive value leakage in outbound metadata.
- Graceful fallback when language models are missing.
- Explicit error handling when unsupported languages or missing models are requested without fallback.
- Custom pattern recognizers for organizational identifiers.
- Deterministic evidence hash generation and bounded sampling.
"""

import json
from unittest.mock import patch
import pandas as pd
import pytest

from engines.pii_detector import (
    CustomPatternRecognizerConfig,
    LanguageModelUnavailableError,
    PIIDetectionError,
    PIIDetector,
    PIIDetectorConfig,
    PIISeverity,
    UnsupportedLanguageError,
)
from engines.pii_detector.exceptions import InvalidDatasetError


@pytest.fixture
def standard_detector():
    """Default detector with standard configuration and spaCy en_core_web_sm."""
    config = PIIDetectorConfig(confidence_threshold=0.4, spacy_model_name="en_core_web_sm")
    return PIIDetector(config=config)


@pytest.fixture
def fallback_detector():
    """Detector configured with pattern-only NoOp fallback engine."""
    config = PIIDetectorConfig(
        confidence_threshold=0.4,
        spacy_model_name="nonexistent_mock_model_xyz",
        allow_nlp_fallback=True,
    )
    return PIIDetector(config=config)


def test_detect_email_addresses(standard_detector):
    """Verify that email addresses are accurately detected with HIGH severity."""
    df = pd.DataFrame({
        "customer_email": ["john.doe@example.com", "sarah_connor@tech.co.uk", "admin@company.org"]
    })
    report = standard_detector.scan_dataframe(df, dataset_id="ds-email-01", version_number=1)

    assert report.has_high_pii is True
    findings = [f for f in report.findings if f.entity_type == "EMAIL_ADDRESS"]
    assert len(findings) == 1
    email_finding = findings[0]
    assert email_finding.column_name == "customer_email"
    assert email_finding.occurrence_count == 3
    assert email_finding.severity == PIISeverity.HIGH
    assert email_finding.confidence >= 0.8
    assert email_finding.evidence_ref.matched_count == 3


def test_detect_phone_numbers(standard_detector):
    """Verify telephone numbers are detected with HIGH severity."""
    df = pd.DataFrame({
        "contact_num": ["(555) 234-5678", "415-555-0199", "+1-800-555-0143"]
    })
    report = standard_detector.scan_dataframe(df, dataset_id="ds-phone-01", version_number=1)

    findings = [f for f in report.findings if f.entity_type == "PHONE_NUMBER"]
    assert len(findings) >= 1
    assert findings[0].severity == PIISeverity.HIGH
    assert findings[0].occurrence_count >= 2


def test_detect_person_names(standard_detector):
    """Verify personal names are detected via spaCy NER."""
    df = pd.DataFrame({
        "full_name": ["Alice Walker", "Robert Oppenheimer", "Ada Lovelace"]
    })
    report = standard_detector.scan_dataframe(df, dataset_id="ds-names-01", version_number=1)

    findings = [f for f in report.findings if f.entity_type == "PERSON"]
    assert len(findings) == 1
    assert findings[0].severity == PIISeverity.HIGH
    assert findings[0].occurrence_count >= 2


def test_detect_ip_addresses(standard_detector):
    """Verify IP addresses are detected with MEDIUM severity."""
    df = pd.DataFrame({
        "client_ip": ["192.168.1.105", "10.0.0.1", "172.16.254.1"]
    })
    report = standard_detector.scan_dataframe(df, dataset_id="ds-ip-01", version_number=1)

    findings = [f for f in report.findings if f.entity_type == "IP_ADDRESS"]
    assert len(findings) == 1
    assert findings[0].severity == PIISeverity.MEDIUM
    assert findings[0].occurrence_count == 3


def test_detect_credit_cards_and_ssn(standard_detector):
    """Verify high-impact identity and financial credentials trigger CRITICAL severity."""
    df = pd.DataFrame({
        "ssn_col": ["123-45-6789", "987-65-4321", "000-12-3456"],
        "cc_col": ["4532-1488-1234-5678", "5424-0000-0000-0001", "3782-822463-10005"],
    })
    report = standard_detector.scan_dataframe(df, dataset_id="ds-crit-01", version_number=1)

    assert report.has_critical_pii is True
    critical_findings = [f for f in report.findings if f.severity == PIISeverity.CRITICAL]
    assert len(critical_findings) >= 1


def test_empty_columns_and_all_nulls(standard_detector):
    """Verify that empty datasets or columns with only nulls/empty strings produce zero false positives."""
    df = pd.DataFrame({
        "all_nulls": [None, None, None],
        "all_empty_strings": ["", "   ", "\t\n"],
        "standard_integers": [101, 102, 103],
    })
    report = standard_detector.scan_dataframe(df, dataset_id="ds-empty-01", version_number=1)

    null_summary = next(c for c in report.columns if c.column_name == "all_nulls")
    assert null_summary.pii_detected is False
    assert null_summary.total_scanned_rows == 0
    assert len(null_summary.findings) == 0

    empty_summary = next(c for c in report.columns if c.column_name == "all_empty_strings")
    assert empty_summary.pii_detected is False
    assert len(empty_summary.findings) == 0


def test_multiple_sensitive_entities_in_one_column(standard_detector):
    """Verify that a column containing multiple distinct PII types produces separate findings."""
    df = pd.DataFrame({
        "free_text_notes": [
            "Customer John Doe reported an issue via jdoe@example.org",
            "Follow-up with 415-555-9876 regarding IP 192.168.1.50",
            "No PII here in this third note",
        ]
    })
    report = standard_detector.scan_dataframe(df, dataset_id="ds-mixed-01", version_number=1)

    col = next(c for c in report.columns if c.column_name == "free_text_notes")
    assert col.pii_detected is True
    entity_types = {f.entity_type for f in col.findings}
    # Should detect multiple entity types from the mixed notes
    assert "EMAIL_ADDRESS" in entity_types
    assert len(entity_types) >= 2


def test_zero_raw_value_leakage_in_cloud_metadata(standard_detector):
    """
    CRITICAL PRIVACY TEST:
    Assert that actual sensitive strings never enter findings, evidence_ref,
    or the outbound cloud metadata dictionary.
    """
    secret_email = "super_secret_ceo@classified-domain.io"
    secret_name = "Alexander Von Secret"
    secret_phone = "555-888-9999"
    secret_ssn = "999-88-7777"

    df = pd.DataFrame({
        "confidential_data": [
            f"Record for {secret_name} with email {secret_email}",
            f"Direct contact: {secret_phone}, SSN reference: {secret_ssn}",
        ]
    })

    report = standard_detector.scan_dataframe(df, dataset_id="leak-test-01", version_number=1)
    cloud_payload = report.to_cloud_metadata()

    # Serialize entire outbound payload to JSON string
    serialized_payload = json.dumps(cloud_payload)

    # Verify that NONE of the raw sensitive values appear anywhere in the metadata payload
    for secret in [secret_email, secret_name, secret_phone, secret_ssn]:
        assert secret not in serialized_payload, f"LEAK DETECTED: Found raw sensitive value '{secret}' in cloud metadata!"

    # Verify that evidence references contain statistical summaries rather than raw text
    for finding in report.findings:
        evidence = finding.evidence_ref
        assert hasattr(evidence, "evidence_hash")
        assert len(evidence.evidence_hash) == 64  # Valid SHA-256
        assert isinstance(evidence.sample_row_indices, list)
        assert isinstance(evidence.length_distribution, dict)


def test_missing_model_graceful_fallback():
    """Verify that when configured with an unavailable model and allow_nlp_fallback=True, it falls back to NoOpNlpEngine."""
    config = PIIDetectorConfig(
        spacy_model_name="totally_nonexistent_model_12345",
        allow_nlp_fallback=True,
    )
    detector = PIIDetector(config=config)
    assert detector.nlp_engine_status == "pattern_fallback:noop"

    # Pattern-based recognition (e.g. EMAIL_ADDRESS, IP_ADDRESS) must still work without spaCy
    df = pd.DataFrame({
        "email_col": ["worker@subdomain.net", "tester@domain.com"],
        "ip_col": ["10.0.1.20", "192.168.0.1"],
    })
    report = detector.scan_dataframe(df, dataset_id="ds-fallback-01", version_number=1)
    assert report.summary.nlp_engine == "pattern_fallback:noop"
    detected_types = {f.entity_type for f in report.findings}
    assert "EMAIL_ADDRESS" in detected_types
    assert "IP_ADDRESS" in detected_types


def test_missing_model_raises_when_fallback_disabled():
    """Verify that when allow_nlp_fallback=False and the model is missing, LanguageModelUnavailableError is raised."""
    config = PIIDetectorConfig(
        spacy_model_name="missing_model_strict_mode",
        allow_nlp_fallback=False,
    )
    with pytest.raises(LanguageModelUnavailableError):
        PIIDetector(config=config)


def test_unsupported_language_raises():
    """Verify that unsupported language codes raise UnsupportedLanguageError when fallback is disabled."""
    config = PIIDetectorConfig(
        language="zh",  # Chinese is not in default spaCy models
        allow_nlp_fallback=False,
    )
    with pytest.raises(UnsupportedLanguageError):
        PIIDetector(config=config)


def test_custom_pattern_recognizer():
    """Verify that custom organization pattern recognizers function properly."""
    custom_emp = CustomPatternRecognizerConfig(
        name="internal_emp_id",
        supported_entity="INTERNAL_EMPLOYEE_ID",
        patterns=[{"name": "emp_code", "regex": r"\bEMP-[A-Z]{2}-\d{4}\b", "score": 0.95}],
        severity=PIISeverity.HIGH,
    )
    config = PIIDetectorConfig(
        confidence_threshold=0.5,
        custom_recognizers=[custom_emp],
    )
    detector = PIIDetector(config=config)

    df = pd.DataFrame({
        "staff_ref": ["EMP-CA-1024", "EMP-NY-9912", "NOT_AN_EMPLOYEE_CODE"],
    })
    report = detector.scan_dataframe(df, dataset_id="ds-custom-01", version_number=1)

    custom_findings = [f for f in report.findings if f.entity_type == "INTERNAL_EMPLOYEE_ID"]
    assert len(custom_findings) == 1
    assert custom_findings[0].occurrence_count == 2
    assert custom_findings[0].severity == PIISeverity.HIGH
    assert custom_findings[0].confidence >= 0.9


def test_severity_overrides():
    """Verify that severity_overrides config updates the reported severity."""
    config = PIIDetectorConfig(
        severity_overrides={"IP_ADDRESS": PIISeverity.CRITICAL}
    )
    detector = PIIDetector(config=config)

    df = pd.DataFrame({"ip": ["127.0.0.1", "10.0.0.1"]})
    report = detector.scan_dataframe(df, dataset_id="ds-override-01", version_number=1)

    ip_finding = next(f for f in report.findings if f.entity_type == "IP_ADDRESS")
    assert ip_finding.severity == PIISeverity.CRITICAL
    assert report.has_critical_pii is True


def test_scan_dataset_bytes_csv(standard_detector):
    """Verify scanning raw CSV bytes end-to-end."""
    csv_bytes = b"user,email,role\nAlice,alice@test.org,Admin\nBob,bob@test.org,User\n"
    report = standard_detector.scan_dataset_bytes(
        content=csv_bytes,
        file_format="csv",
        dataset_id="ds-csv-bytes",
        version_number=1,
    )
    assert report.dataset_id == "ds-csv-bytes"
    assert report.summary.total_rows_scanned == 2
    assert report.summary.total_columns_scanned == 3
    assert any(f.entity_type == "EMAIL_ADDRESS" for f in report.findings)


def test_empty_dataset_raises_invalid_dataset_error(standard_detector):
    """Verify scanning completely empty dataframe raises InvalidDatasetError."""
    empty_df = pd.DataFrame()
    with pytest.raises(InvalidDatasetError):
        standard_detector.scan_dataframe(empty_df, dataset_id="empty-01", version_number=1)


def test_bounded_sampling():
    """Verify that max_rows_to_sample caps the number of evaluated rows."""
    config = PIIDetectorConfig(max_rows_to_sample=2)
    detector = PIIDetector(config=config)

    df = pd.DataFrame({
        "emails": [
            "one@example.com",
            "two@example.com",
            "three@example.com",
            "four@example.com",
        ]
    })
    report = detector.scan_dataframe(df, dataset_id="ds-sample-01", version_number=1)
    col = next(c for c in report.columns if c.column_name == "emails")
    assert col.total_scanned_rows == 2
    finding = next(f for f in col.findings if f.entity_type == "EMAIL_ADDRESS")
    assert finding.occurrence_count == 2
