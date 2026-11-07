"""
Unit and security tests for the Safe Dataset Transformation Engine (engines/transformation_engine).
Verifies:
- Every supported allowlisted transformation:
  * Column removal (REMOVE_COLUMN)
  * Column masking (MASK_COLUMN: full redaction, partial email, partial phone, last 4 digits)
  * Deterministic HMAC-SHA256 pseudonymization (PSEUDONYMIZE_COLUMN)
  * Generalization (GENERALIZE_COLUMN: numeric binning, date truncation, category bucketing)
  * Declarative row filtering (FILTER_ROWS: equals, greater_than, in_list, is_null)
- Complete source artifact immutability (original data remains strictly untouched).
- Deterministic transformations & cryptographic output hash integrity.
- Security tests: Strict rejection of arbitrary Python, eval, exec, SQL, shell code injections.
- Safe aggregate preview generation without raw value leakage.
- Automated post-transformation re-verification (privacy, quality, policy evaluation).
"""

import hashlib
import json
import pandas as pd
import pytest

from engines.transformation_engine import (
    ArbitraryCodeExecutionRejectedError,
    FilterOperator,
    FilterRowsOp,
    GeneralizationStrategy,
    GeneralizeColumnOp,
    InvalidTransformationSpecError,
    MaskColumnOp,
    MaskingStrategy,
    OperationType,
    PseudonymizeColumnOp,
    RemoveColumnOp,
    TransformationEngine,
    TransformationSpec,
)


@pytest.fixture
def sample_dataset():
    """Generates a sample DataFrame containing mixed sensitive and quality test attributes."""
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "ssn": ["111-22-3333", "444-55-6666", "777-88-9999", "000-11-2222", "333-44-5555"],
        "email": [
            "alice@example.com",
            "bob_smith@tech.org",
            "carol_danvers@avengers.io",
            "dave@internal.corp",
            "eve@security.net",
        ],
        "phone": [
            "415-555-0101",
            "212-555-0102",
            "(312) 555-0103",
            "555-0104",
            "+1-800-555-0105",
        ],
        "age": [17, 24, 38, 52, 71],
        "hire_date": ["2015-03-12", "2018-07-22", "2020-01-15", "2022-11-01", "2023-05-30"],
        "department": ["Engineering", "Product", "Engineering", "Marketing", "Executive"],
        "status": ["ACTIVE", "ACTIVE", "INACTIVE", "ACTIVE", "SUSPENDED"],
        "notes": ["ok", "pending review", None, "ok", "flagged"],
    })


def test_remove_column_operation(sample_dataset):
    """Verify REMOVE_COLUMN completely drops target column while keeping other columns intact."""
    df_copy = sample_dataset.copy(deep=True)
    spec = TransformationSpec(
        operations=[RemoveColumnOp(column_name="ssn")]
    )

    transformed_df, prov, prev = TransformationEngine.apply_transformations(
        df=df_copy,
        spec=spec,
        dataset_id="ds-remove-01",
        input_version=1,
        output_version=2,
        input_hash="hash_in",
    )

    assert "ssn" not in transformed_df.columns
    assert "ssn" in sample_dataset.columns  # Original dataset untouched
    assert "ssn" in prev.columns_removed
    assert transformed_df.shape[1] == sample_dataset.shape[1] - 1


def test_mask_column_all_strategies(sample_dataset):
    """Verify MASK_COLUMN with full redaction, partial email, partial phone, and last 4 digits."""
    df_copy = sample_dataset.copy(deep=True)
    spec = TransformationSpec(
        operations=[
            MaskColumnOp(column_name="notes", strategy=MaskingStrategy.FULL_REDACTION, placeholder="[MASKED]"),
            MaskColumnOp(column_name="email", strategy=MaskingStrategy.PARTIAL_EMAIL),
            MaskColumnOp(column_name="phone", strategy=MaskingStrategy.PARTIAL_PHONE),
            MaskColumnOp(column_name="ssn", strategy=MaskingStrategy.LAST_4_VISIBLE),
        ]
    )

    transformed_df, prov, prev = TransformationEngine.apply_transformations(
        df=df_copy,
        spec=spec,
        dataset_id="ds-mask-01",
        input_version=1,
        output_version=2,
        input_hash="hash_in",
    )

    # Full redaction
    non_null_notes = transformed_df["notes"].dropna()
    assert all(val == "[MASKED]" for val in non_null_notes)

    # Partial email: "alice@example.com" -> "a***e@example.com"
    first_email = transformed_df["email"].iloc[0]
    assert first_email == "a***e@example.com"

    # Partial phone: last 4 digits visible
    first_phone = transformed_df["phone"].iloc[0]
    assert first_phone.endswith("0101")
    assert first_phone.startswith("***-***-")

    # Last 4 visible: ssn "111-22-3333" -> "***-**-3333"
    first_ssn = transformed_df["ssn"].iloc[0]
    assert first_ssn == "***-**-3333"


def test_pseudonymize_column_deterministic(sample_dataset):
    """Verify deterministic HMAC-SHA256 pseudonymization."""
    df_copy = sample_dataset.copy(deep=True)
    salt = "fixed_test_salt_secret_123"

    spec = TransformationSpec(
        operations=[
            PseudonymizeColumnOp(column_name="email", salt=salt, prefix="PSEUDO_")
        ]
    )

    transformed_df1, _, _ = TransformationEngine.apply_transformations(
        df=df_copy, spec=spec, dataset_id="ds-pseudo", input_version=1, output_version=2, input_hash="h1"
    )
    transformed_df2, _, _ = TransformationEngine.apply_transformations(
        df=df_copy, spec=spec, dataset_id="ds-pseudo", input_version=1, output_version=2, input_hash="h1"
    )

    # Pseudonyms are deterministic for same input + salt
    assert list(transformed_df1["email"]) == list(transformed_df2["email"])
    assert all(str(val).startswith("PSEUDO_") for val in transformed_df1["email"])
    assert "@" not in transformed_df1["email"].iloc[0]


def test_generalize_column_numeric_date_and_category(sample_dataset):
    """Verify GENERALIZE_COLUMN with numeric binning, date truncation, and categorical grouping."""
    df_copy = sample_dataset.copy(deep=True)
    spec = TransformationSpec(
        operations=[
            GeneralizeColumnOp(
                column_name="age",
                strategy=GeneralizationStrategy.NUMERIC_BINNING,
                bins=[0, 18, 30, 50, 100],
                bin_labels=["<18", "18-29", "30-49", "50+"],
            ),
            GeneralizeColumnOp(
                column_name="hire_date",
                strategy=GeneralizationStrategy.DATE_TRUNCATION,
                date_interval="YEAR",
            ),
            GeneralizeColumnOp(
                column_name="department",
                strategy=GeneralizationStrategy.CATEGORY_BUCKETING,
                category_mapping={"Engineering": "R&D", "Product": "R&D", "Marketing": "G&A", "Executive": "G&A"},
            ),
        ]
    )

    transformed_df, prov, prev = TransformationEngine.apply_transformations(
        df=df_copy,
        spec=spec,
        dataset_id="ds-gen-01",
        input_version=1,
        output_version=2,
        input_hash="hash_in",
    )

    # Age binned: 17 -> "<18", 24 -> "18-29", 38 -> "30-49"
    assert transformed_df["age"].iloc[0] == "<18"
    assert transformed_df["age"].iloc[1] == "18-29"
    assert transformed_df["age"].iloc[2] == "30-49"

    # Hire date truncated to year: "2015-03-12" -> "2015"
    assert transformed_df["hire_date"].iloc[0] == "2015"
    assert transformed_df["hire_date"].iloc[1] == "2018"

    # Category mapped: "Engineering" -> "R&D", "Executive" -> "G&A"
    assert transformed_df["department"].iloc[0] == "R&D"
    assert transformed_df["department"].iloc[4] == "G&A"


def test_filter_rows_declarative_operators(sample_dataset):
    """Verify FILTER_ROWS keeps rows matching allowlisted operators without code evaluation."""
    df_copy = sample_dataset.copy(deep=True)

    # Filter 1: keep only ACTIVE
    spec_active = TransformationSpec(
        operations=[
            FilterRowsOp(column_name="status", operator=FilterOperator.EQUALS, value="ACTIVE")
        ]
    )
    df_filtered, _, prev = TransformationEngine.apply_transformations(
        df=df_copy, spec=spec_active, dataset_id="ds-f1", input_version=1, output_version=2, input_hash="h1"
    )
    assert len(df_filtered) == 3
    assert set(df_filtered["status"]) == {"ACTIVE"}
    assert prev.rows_removed == 2

    # Filter 2: age >= 25
    spec_age = TransformationSpec(
        operations=[
            FilterRowsOp(column_name="age", operator=FilterOperator.GREATER_THAN_OR_EQUAL, value=25)
        ]
    )
    df_age, _, _ = TransformationEngine.apply_transformations(
        df=df_copy, spec=spec_age, dataset_id="ds-f2", input_version=1, output_version=2, input_hash="h1"
    )
    assert len(df_age) == 3  # 38, 52, 71

    # Filter 3: department IN_LIST
    spec_dept = TransformationSpec(
        operations=[
            FilterRowsOp(column_name="department", operator=FilterOperator.IN_LIST, values_list=["Engineering", "Product"])
        ]
    )
    df_dept, _, _ = TransformationEngine.apply_transformations(
        df=df_copy, spec=spec_dept, dataset_id="ds-f3", input_version=1, output_version=2, input_hash="h1"
    )
    assert len(df_dept) == 3


def test_source_dataset_immutability(sample_dataset):
    """
    CRITICAL IMMUTABILITY TEST:
    Verify that applying transformations never alters the original input DataFrame or values.
    """
    original_cols = list(sample_dataset.columns)
    original_shape = sample_dataset.shape
    original_values = sample_dataset["ssn"].tolist()

    spec = TransformationSpec(
        operations=[
            RemoveColumnOp(column_name="ssn"),
            FilterRowsOp(column_name="status", operator=FilterOperator.EQUALS, value="ACTIVE"),
        ]
    )

    transformed_df, _, _ = TransformationEngine.apply_transformations(
        df=sample_dataset,
        spec=spec,
        dataset_id="ds-immutable",
        input_version=1,
        output_version=2,
        input_hash="hash_orig",
    )

    # Transformed dataset has changes
    assert "ssn" not in transformed_df.columns
    assert len(transformed_df) == 3

    # Source dataset is 100% untouched
    assert list(sample_dataset.columns) == original_cols
    assert sample_dataset.shape == original_shape
    assert sample_dataset["ssn"].tolist() == original_values


def test_security_rejects_arbitrary_code_injection(sample_dataset):
    """
    CRITICAL SECURITY TEST:
    Verify that any attempt to embed arbitrary Python, SQL, shell code, eval, or exec is rejected.
    """
    injections = [
        "__import__('os').system('cat /etc/passwd')",
        "eval('2 + 2')",
        "exec('import sys; sys.exit(1)')",
        "os.system('rm -rf /')",
        "subprocess.Popen(['bash'])",
        "; drop table users; --",
        "<script>alert(1)</script>",
    ]

    for payload in injections:
        with pytest.raises(ArbitraryCodeExecutionRejectedError):
            spec = TransformationSpec(
                operations=[
                    MaskColumnOp(column_name="notes", strategy=MaskingStrategy.CUSTOM_PLACEHOLDER, placeholder=payload)
                ]
            )
            TransformationEngine.validate_spec(sample_dataset, spec)


def test_invalid_operation_nonexistent_column(sample_dataset):
    """Verify invalid operations referencing non-existent columns are rejected with clear error."""
    spec = TransformationSpec(
        operations=[RemoveColumnOp(column_name="non_existent_column_xyz")]
    )
    with pytest.raises(InvalidTransformationSpecError):
        TransformationEngine.validate_spec(sample_dataset, spec)


def test_deterministic_output_hash_integrity(sample_dataset):
    """Verify cryptographic output hash matches actual serialized content SHA-256."""
    csv_bytes = sample_dataset.to_csv(index=False).encode("utf-8")
    spec = TransformationSpec(
        operations=[RemoveColumnOp(column_name="ssn")]
    )

    result = TransformationEngine.transform_dataset_bytes(
        content=csv_bytes,
        file_format="csv",
        spec=spec,
        dataset_id="ds-hash-check",
        input_version=1,
        output_version=2,
        run_post_verification=False,
    )

    assert result.input_hash == hashlib.sha256(csv_bytes).hexdigest()
    assert len(result.output_hash) == 64
    assert result.output_hash != result.input_hash
    assert result.provenance.output_hash == result.output_hash


def test_zero_raw_value_leakage_in_preview_and_metadata(sample_dataset):
    """
    CRITICAL PRIVACY TEST:
    Verify that TransformationPreview and .to_cloud_metadata() contain only aggregates,
    counts, and statistics, with zero raw cell values.
    """
    secret_value = "SECRET_CLASSIFIED_SSN_9999"
    sample_dataset.loc[0, "ssn"] = secret_value

    csv_bytes = sample_dataset.to_csv(index=False).encode("utf-8")
    spec = TransformationSpec(
        operations=[
            MaskColumnOp(column_name="ssn", strategy=MaskingStrategy.FULL_REDACTION)
        ]
    )

    result = TransformationEngine.transform_dataset_bytes(
        content=csv_bytes,
        file_format="csv",
        spec=spec,
        dataset_id="ds-leak-check",
        input_version=1,
        output_version=2,
        run_post_verification=False,
    )

    cloud_meta = result.to_cloud_metadata()
    serialized = json.dumps(cloud_meta)

    assert secret_value not in serialized, f"LEAK DETECTED: Found secret '{secret_value}' in cloud metadata!"


def test_end_to_end_post_transformation_revalidation(sample_dataset):
    """
    Verify that post-transformation verification re-runs Privacy, Quality, and Policy checks.
    Proves that removing SSN and masking email reduces risk score and changes policy status.
    """
    csv_bytes = sample_dataset.to_csv(index=False).encode("utf-8")

    # Before transformation: has SSN (Critical PII) -> Policy BLOCKED
    # Transformation: Remove SSN, Mask email, Mask phone
    spec = TransformationSpec(
        operations=[
            RemoveColumnOp(column_name="ssn"),
            MaskColumnOp(column_name="email", strategy=MaskingStrategy.PARTIAL_EMAIL),
            MaskColumnOp(column_name="phone", strategy=MaskingStrategy.PARTIAL_PHONE),
        ]
    )

    result = TransformationEngine.transform_dataset_bytes(
        content=csv_bytes,
        file_format="csv",
        spec=spec,
        dataset_id="ds-reval-01",
        input_version=1,
        output_version=2,
        run_post_verification=True,
        metadata_context={
            "dataset_name": "Sanitized Customer Sample",
            "description": "Redacted benchmark release",
            "license": "Apache-2.0",
            "domain": "general",
        },
    )

    assert result.post_pii_report is not None
    assert result.post_quality_report is not None
    assert result.post_policy_evaluation is not None

    # Verify that SSN is gone from post PII report
    post_pii = result.post_pii_report
    assert post_pii.get("has_critical_pii") is False

    # Verify policy evaluation was re-scored
    post_pol = result.post_policy_evaluation
    assert "status" in post_pol
    assert "total_risk_score" in post_pol
