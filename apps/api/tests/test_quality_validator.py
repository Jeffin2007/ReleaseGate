"""
Unit tests for the Deterministic Data Quality Validator Engine (engines/quality_validator).
Verifies:
- Missing values and nullability constraints (allow_null, max_null_percentage, global nulls).
- Duplicate records (dataset-wide duplicates and column-level uniqueness).
- Invalid date formats (e.g. ISO-8601 or custom strftime).
- Numeric range limits, out-of-bounds numbers, and malformed non-numeric values.
- Allowed values enumeration constraints.
- Regex pattern validation.
- Inconsistent data types and expected dtypes.
- Empty datasets and malformed schemas.
- Strict reproducibility across repeated runs (identical scores, issue counts, evidence hashes).
- Zero raw value leakage in outbound cloud metadata.
- End-to-end dataset bytes validation and LocalIngestionWorker integration.
"""

import json
import uuid
import pandas as pd
import pytest

from engines.quality_validator import (
    ColumnRule,
    DatasetLevelRules,
    InvalidDatasetForValidation,
    QualityReport,
    QualitySeverity,
    QualityValidationConfig,
    QualityValidator,
    RuleType,
)


@pytest.fixture
def base_config():
    """Default quality validation config with duplicate check enabled."""
    return QualityValidationConfig()


def test_missing_values_and_nullability():
    """Verify null checks trigger issues when allow_null=False or max_null_percentage is exceeded."""
    df = pd.DataFrame({
        "id": [1, 2, None, 4],
        "optional_notes": ["a", None, None, "d"],
        "strict_code": ["c1", "c2", "c3", "c4"],
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="id", allow_null=False, severity=QualitySeverity.CRITICAL),
            ColumnRule(column_name="optional_notes", max_null_percentage=25.0),  # 2 of 4 is 50% -> fails
            ColumnRule(column_name="strict_code", allow_null=False),  # 0 nulls -> passes
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-nulls-01", version_number=1)

    assert report.summary.total_rules_evaluated >= 4
    assert report.summary.has_critical_failures is True

    # Check id failure
    id_issue = next(i for i in report.issues if i.column_name == "id" and i.rule_type == RuleType.NOT_NULL)
    assert id_issue.violating_count == 1
    assert id_issue.severity == QualitySeverity.CRITICAL
    assert 2 in id_issue.evidence_ref.sample_row_indices

    # Check optional_notes failure
    notes_issue = next(i for i in report.issues if i.column_name == "optional_notes")
    assert notes_issue.violating_count == 2
    assert notes_issue.violating_percentage == 50.0

    # strict_code passed
    strict_res = next(r for r in report.rule_results if r.column_name == "strict_code")
    assert strict_res.passed is True


def test_duplicate_records_dataset_and_column():
    """Verify duplicate row detection and column uniqueness constraints."""
    df = pd.DataFrame({
        "order_id": ["ORD-101", "ORD-102", "ORD-103", "ORD-101"],
        "amount": [50.0, 75.0, 100.0, 50.0],
    })

    config = QualityValidationConfig(
        dataset_rules=DatasetLevelRules(no_duplicate_rows=True, duplicate_rows_severity=QualitySeverity.HIGH),
        column_rules=[
            ColumnRule(column_name="order_id", unique=True, severity=QualitySeverity.HIGH)
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-dups-01", version_number=1)

    # Dataset-level duplicate row
    dup_row_issue = next(i for i in report.issues if i.rule_type == RuleType.NO_DUPLICATE_ROWS)
    assert dup_row_issue.violating_count == 1

    # Column uniqueness violation
    col_dup_issue = next(i for i in report.issues if i.rule_type == RuleType.UNIQUE)
    assert col_dup_issue.column_name == "order_id"
    assert col_dup_issue.violating_count == 1


def test_invalid_dates():
    """Verify datetime format validation catches malformed date strings."""
    df = pd.DataFrame({
        "event_date": ["2023-01-01", "2023-02-29", "invalid-date", "2023-12-31"]  # 2023 is not a leap year
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="event_date", date_format="%Y-%m-%d")
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-dates-01", version_number=1)

    date_issue = next(i for i in report.issues if i.rule_type == RuleType.DATE_FORMAT)
    assert date_issue.column_name == "event_date"
    assert date_issue.violating_count == 2  # "2023-02-29" and "invalid-date"
    assert 1 in date_issue.evidence_ref.sample_row_indices
    assert 2 in date_issue.evidence_ref.sample_row_indices


def test_numeric_range_and_malformed_values():
    """Verify numeric range [min, max] flags both out-of-range values and non-numeric strings."""
    df = pd.DataFrame({
        "age": [25, 45, -2, 135, "not_a_number", 60]
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="age", min_value=0, max_value=120)
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-num-01", version_number=1)

    range_issue = next(i for i in report.issues if i.rule_type == RuleType.NUMERIC_RANGE)
    assert range_issue.column_name == "age"
    # -2 (below min), 135 (above max), "not_a_number" (malformed non-numeric) -> 3 violations
    assert range_issue.violating_count == 3
    assert range_issue.evidence_ref.details["malformed_non_numeric_count"] == 1


def test_allowed_values_enum_constraint():
    """Verify allowed_values rule flags any item outside the allowed set."""
    df = pd.DataFrame({
        "status": ["APPROVED", "PENDING", "REJECTED", "CORRUPTED_STATUS", "PENDING"]
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="status", allowed_values=["APPROVED", "PENDING", "REJECTED"])
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-enum-01", version_number=1)

    enum_issue = next(i for i in report.issues if i.rule_type == RuleType.ALLOWED_VALUES)
    assert enum_issue.column_name == "status"
    assert enum_issue.violating_count == 1
    assert 3 in enum_issue.evidence_ref.sample_row_indices


def test_regex_pattern_validation():
    """Verify regex pattern rules catch malformed strings."""
    df = pd.DataFrame({
        "sku": ["SKU-1001", "SKU-9999", "INVALID-SKU", "SKU-ABC"]
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="sku", regex_pattern=r"^SKU-\d{4}$")
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-sku-01", version_number=1)

    regex_issue = next(i for i in report.issues if i.rule_type == RuleType.REGEX_FORMAT)
    assert regex_issue.column_name == "sku"
    assert regex_issue.violating_count == 2
    assert 2 in regex_issue.evidence_ref.sample_row_indices
    assert 3 in regex_issue.evidence_ref.sample_row_indices


def test_inconsistent_and_expected_dtype():
    """Verify expected_dtype catches mismatched semantic column types."""
    df = pd.DataFrame({
        "price_string": ["10.5", "20.0", "35.5"],  # Pandas dtype object / string
        "valid_int": [1, 2, 3],
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="price_string", expected_dtype="float"),
            ColumnRule(column_name="valid_int", expected_dtype="integer"),
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-dtype-01", version_number=1)

    # price_string was stored as string instead of numeric float
    mismatch_issue = next(i for i in report.issues if i.column_name == "price_string")
    assert mismatch_issue.rule_type == RuleType.EXPECTED_DTYPE

    # valid_int passes
    int_res = next(r for r in report.rule_results if r.column_name == "valid_int")
    assert int_res.passed is True


def test_empty_dataset_raises_invalid_dataset_error():
    """Verify validating an empty dataset raises InvalidDatasetForValidation."""
    empty_df = pd.DataFrame()
    validator = QualityValidator()

    with pytest.raises(InvalidDatasetForValidation):
        validator.validate_dataframe(empty_df, dataset_id="empty-ds", version_number=1)


def test_required_columns_schema_validation():
    """Verify missing required columns trigger critical issues."""
    df = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})

    config = QualityValidationConfig(
        dataset_rules=DatasetLevelRules(required_columns=["col_a", "col_missing_1", "col_missing_2"])
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-schema-01", version_number=1)

    schema_issue = next(i for i in report.issues if i.rule_name == "dataset:required_columns")
    assert schema_issue.severity == QualitySeverity.CRITICAL
    assert schema_issue.violating_count == 2
    assert "col_missing_1" in schema_issue.evidence_ref.details["missing_columns"]
    assert "col_missing_2" in schema_issue.evidence_ref.details["missing_columns"]


def test_reproducibility_across_repeated_runs():
    """
    CRITICAL REPRODUCIBILITY TEST:
    Verify that identical inputs produce 100% identical reports, issue counts, and evidence hashes.
    """
    df = pd.DataFrame({
        "id": [1, 2, 2, 4, None],
        "category": ["A", "B", "C", "INVALID", "A"],
        "score": [50.0, 110.0, 75.0, 80.0, -5.0],
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="id", allow_null=False, unique=True),
            ColumnRule(column_name="category", allowed_values=["A", "B", "C"]),
            ColumnRule(column_name="score", min_value=0.0, max_value=100.0),
        ]
    )
    validator = QualityValidator(config=config)

    fixed_run_id = "test-run-reproducible-uuid"
    report_run1 = validator.validate_dataframe(
        df, dataset_id="ds-repro-01", version_number=1, inspection_run_id=fixed_run_id
    )
    report_run2 = validator.validate_dataframe(
        df, dataset_id="ds-repro-01", version_number=1, inspection_run_id=fixed_run_id
    )

    # Validate identical summaries
    assert report_run1.summary.quality_score == report_run2.summary.quality_score
    assert report_run1.summary.total_rules_evaluated == report_run2.summary.total_rules_evaluated
    assert report_run1.summary.passed_rules_count == report_run2.summary.passed_rules_count
    assert report_run1.summary.failed_rules_count == report_run2.summary.failed_rules_count
    assert report_run1.summary.affected_columns == report_run2.summary.affected_columns

    # Validate identical issues and hashes
    assert len(report_run1.issues) == len(report_run2.issues)
    for issue1, issue2 in zip(report_run1.issues, report_run2.issues):
        assert issue1.rule_name == issue2.rule_name
        assert issue1.violating_count == issue2.violating_count
        assert issue1.violating_percentage == issue2.violating_percentage
        assert issue1.evidence_ref.evidence_hash == issue2.evidence_ref.evidence_hash
        assert issue1.evidence_ref.sample_row_indices == issue2.evidence_ref.sample_row_indices


def test_zero_raw_value_leakage_in_cloud_metadata():
    """
    CRITICAL PRIVACY TEST:
    Verify that raw violating cell values NEVER enter the outbound cloud metadata dictionary.
    """
    secret_value = "HIGHLY_CONFIDENTIAL_ORGANIZATION_SECRET_VALUE"
    secret_number = 999999999.88

    df = pd.DataFrame({
        "status": ["ALLOWED_1", secret_value],
        "metric": [10.0, secret_number],
    })

    config = QualityValidationConfig(
        column_rules=[
            ColumnRule(column_name="status", allowed_values=["ALLOWED_1"]),
            ColumnRule(column_name="metric", min_value=0, max_value=100),
        ]
    )
    validator = QualityValidator(config=config)
    report = validator.validate_dataframe(df, dataset_id="ds-leak-01", version_number=1)

    cloud_meta = report.to_cloud_metadata()
    serialized = json.dumps(cloud_meta)

    assert secret_value not in serialized, f"LEAK DETECTED: Found '{secret_value}' in cloud metadata!"
    assert str(secret_number) not in serialized, f"LEAK DETECTED: Found numeric value '{secret_number}' in metadata!"


def test_validate_dataset_bytes_csv_and_json():
    """Verify validation of raw CSV and JSON bytes."""
    csv_bytes = b"user_id,role\n100,ADMIN\n200,INVALID_ROLE\n"
    json_bytes = b'[{"user_id": 100, "role": "ADMIN"}, {"user_id": 200, "role": "INVALID_ROLE"}]'

    config = QualityValidationConfig(
        column_rules=[ColumnRule(column_name="role", allowed_values=["ADMIN", "USER"])]
    )
    validator = QualityValidator(config=config)

    # Test CSV bytes
    csv_report = validator.validate_dataset_bytes(
        content=csv_bytes, file_format="csv", dataset_id="ds-csv", version_number=1
    )
    assert csv_report.summary.failed_rules_count >= 1
    assert any(i.column_name == "role" for i in csv_report.issues)

    # Test JSON bytes
    json_report = validator.validate_dataset_bytes(
        content=json_bytes, file_format="json", dataset_id="ds-json", version_number=1
    )
    assert json_report.summary.failed_rules_count >= 1
    assert any(i.column_name == "role" for i in json_report.issues)
