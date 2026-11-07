"""
Deterministic Data Quality Validator Engine.
Executes reproducible local validation rules across tabular datasets:
- Missing values and nullability constraints
- Duplicate records (dataset-wide and column-level uniqueness)
- Invalid formats (regex patterns and date formats)
- Inconsistent data types and malformed numeric values
- Bounded numeric range checks and allowed-value enums
- Zero raw data leakage in outbound summaries and evidence references
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Set
import uuid
import pandas as pd

from engines.dataset_profiler import DatasetProfiler, ProfilingError

from .config import ColumnRule, QualityValidationConfig
from .exceptions import InvalidDatasetForValidation, QualityValidationError
from .schemas import (
    EvidenceReference,
    QualityIssue,
    QualityReport,
    QualityRuleResult,
    QualitySeverity,
    QualitySummary,
    RuleType,
    generate_quality_evidence_hash,
)


class QualityValidator:
    """
    Deterministic dataset quality validation engine.
    Runs locally in Environment B without external API calls or AI hallucinations.
    """

    def __init__(self, config: Optional[QualityValidationConfig] = None) -> None:
        self.config = config or QualityValidationConfig()

    def validate_dataframe(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        version_number: int = 1,
        inspection_run_id: Optional[str] = None,
    ) -> QualityReport:
        """
        Deterministically validate a pandas DataFrame against configured rules.
        """
        if df.empty or len(df.columns) == 0:
            raise InvalidDatasetForValidation(
                "Cannot validate empty dataset (0 rows or 0 columns)."
            )

        run_id = inspection_run_id or str(uuid.uuid4())
        total_rows = int(len(df))
        total_columns = int(len(df.columns))

        rule_results: List[QualityRuleResult] = []
        issues: List[QualityIssue] = []
        affected_columns_set: Set[str] = set()

        # -------------------------------------------------------------
        # 1. Dataset-Level Rules
        # -------------------------------------------------------------
        dataset_rules = self.config.dataset_rules

        # 1A. Required Columns Schema Check
        if dataset_rules.required_columns:
            missing_cols = [
                col for col in dataset_rules.required_columns if col not in df.columns
            ]
            rule_name = "dataset:required_columns"
            passed = len(missing_cols) == 0

            issue = None
            if not passed:
                affected_columns_set.update(missing_cols)
                evidence_hash = generate_quality_evidence_hash(
                    dataset_id=dataset_id,
                    version_number=version_number,
                    rule_name=rule_name,
                    column_name=None,
                    violating_count=len(missing_cols),
                    violating_percentage=round((len(missing_cols) / len(dataset_rules.required_columns)) * 100, 2),
                )
                evidence_ref = EvidenceReference(
                    rule_name=rule_name,
                    rule_type=RuleType.EXPECTED_DTYPE,
                    column_name=None,
                    violating_count=len(missing_cols),
                    violating_percentage=round((len(missing_cols) / len(dataset_rules.required_columns)) * 100, 2),
                    details={"missing_columns": missing_cols},
                    evidence_hash=evidence_hash,
                )
                issue = QualityIssue(
                    rule_name=rule_name,
                    rule_type=RuleType.EXPECTED_DTYPE,
                    column_name=None,
                    severity=QualitySeverity.CRITICAL,
                    message=f"Dataset schema is missing {len(missing_cols)} required columns: {missing_cols}",
                    violating_count=len(missing_cols),
                    violating_percentage=round((len(missing_cols) / len(dataset_rules.required_columns)) * 100, 2),
                    evidence_ref=evidence_ref,
                )
                issues.append(issue)

            rule_results.append(
                QualityRuleResult(
                    rule_name=rule_name,
                    rule_type=RuleType.EXPECTED_DTYPE,
                    column_name=None,
                    passed=passed,
                    severity=QualitySeverity.CRITICAL,
                    issue=issue,
                )
            )

        # 1B. Duplicate Rows Check
        if dataset_rules.no_duplicate_rows:
            rule_name = "dataset:no_duplicate_rows"
            dup_mask = df.duplicated()
            dup_count = int(dup_mask.sum())
            dup_pct = round((dup_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
            passed = dup_count == 0

            issue = None
            if not passed:
                sample_indices = [
                    int(idx) for idx in df[dup_mask].index[: self.config.sample_row_limit]
                ]
                evidence_hash = generate_quality_evidence_hash(
                    dataset_id=dataset_id,
                    version_number=version_number,
                    rule_name=rule_name,
                    column_name=None,
                    violating_count=dup_count,
                    violating_percentage=dup_pct,
                )
                evidence_ref = EvidenceReference(
                    rule_name=rule_name,
                    rule_type=RuleType.NO_DUPLICATE_ROWS,
                    column_name=None,
                    violating_count=dup_count,
                    violating_percentage=dup_pct,
                    sample_row_indices=sample_indices,
                    details={"duplicate_row_count": dup_count},
                    evidence_hash=evidence_hash,
                )
                issue = QualityIssue(
                    rule_name=rule_name,
                    rule_type=RuleType.NO_DUPLICATE_ROWS,
                    column_name=None,
                    severity=dataset_rules.duplicate_rows_severity,
                    message=f"Dataset contains {dup_count} duplicate rows ({dup_pct}% of dataset)",
                    violating_count=dup_count,
                    violating_percentage=dup_pct,
                    evidence_ref=evidence_ref,
                )
                issues.append(issue)

            rule_results.append(
                QualityRuleResult(
                    rule_name=rule_name,
                    rule_type=RuleType.NO_DUPLICATE_ROWS,
                    column_name=None,
                    passed=passed,
                    severity=dataset_rules.duplicate_rows_severity,
                    issue=issue,
                )
            )

        # 1C. Global Total Null Percentage Check
        if dataset_rules.max_total_null_percentage is not None:
            rule_name = "dataset:max_total_null_percentage"
            total_cells = total_rows * total_columns
            total_nulls = int(df.isna().sum().sum())
            null_pct = round((total_nulls / total_cells) * 100, 2) if total_cells > 0 else 0.0
            passed = null_pct <= dataset_rules.max_total_null_percentage

            issue = None
            if not passed:
                evidence_hash = generate_quality_evidence_hash(
                    dataset_id=dataset_id,
                    version_number=version_number,
                    rule_name=rule_name,
                    column_name=None,
                    violating_count=total_nulls,
                    violating_percentage=null_pct,
                )
                evidence_ref = EvidenceReference(
                    rule_name=rule_name,
                    rule_type=RuleType.NOT_NULL,
                    column_name=None,
                    violating_count=total_nulls,
                    violating_percentage=null_pct,
                    details={
                        "observed_null_percentage": null_pct,
                        "threshold_percentage": dataset_rules.max_total_null_percentage,
                    },
                    evidence_hash=evidence_hash,
                )
                issue = QualityIssue(
                    rule_name=rule_name,
                    rule_type=RuleType.NOT_NULL,
                    column_name=None,
                    severity=QualitySeverity.HIGH,
                    message=(
                        f"Dataset total null percentage {null_pct}% exceeds allowed limit "
                        f"{dataset_rules.max_total_null_percentage}%"
                    ),
                    violating_count=total_nulls,
                    violating_percentage=null_pct,
                    evidence_ref=evidence_ref,
                )
                issues.append(issue)

            rule_results.append(
                QualityRuleResult(
                    rule_name=rule_name,
                    rule_type=RuleType.NOT_NULL,
                    column_name=None,
                    passed=passed,
                    severity=QualitySeverity.HIGH,
                    issue=issue,
                )
            )

        # -------------------------------------------------------------
        # 2. Column-Level Rules
        # -------------------------------------------------------------
        for rule in self.config.column_rules:
            col_name = rule.column_name

            # Check if column exists
            if col_name not in df.columns:
                rule_name = f"column:{col_name}:exists"
                affected_columns_set.add(col_name)
                evidence_hash = generate_quality_evidence_hash(
                    dataset_id=dataset_id,
                    version_number=version_number,
                    rule_name=rule_name,
                    column_name=col_name,
                    violating_count=total_rows,
                    violating_percentage=100.0,
                )
                evidence_ref = EvidenceReference(
                    rule_name=rule_name,
                    rule_type=RuleType.EXPECTED_DTYPE,
                    column_name=col_name,
                    violating_count=total_rows,
                    violating_percentage=100.0,
                    details={"error": "Column not found in dataset"},
                    evidence_hash=evidence_hash,
                )
                issue = QualityIssue(
                    rule_name=rule_name,
                    rule_type=RuleType.EXPECTED_DTYPE,
                    column_name=col_name,
                    severity=QualitySeverity.CRITICAL,
                    message=f"Target column '{col_name}' does not exist in dataset",
                    violating_count=total_rows,
                    violating_percentage=100.0,
                    evidence_ref=evidence_ref,
                )
                issues.append(issue)
                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.EXPECTED_DTYPE,
                        column_name=col_name,
                        passed=False,
                        severity=QualitySeverity.CRITICAL,
                        issue=issue,
                    )
                )
                continue

            series = df[col_name]
            null_mask = series.isna()
            null_count = int(null_mask.sum())
            null_pct = round((null_count / total_rows) * 100, 2) if total_rows > 0 else 0.0

            # 2A. Nullability & Max Null Percentage Check
            if not rule.allow_null:
                rule_name = f"column:{col_name}:not_null"
                passed = null_count == 0
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    sample_indices = [
                        int(idx) for idx in series[null_mask].index[: self.config.sample_row_limit]
                    ]
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=null_count,
                        violating_percentage=null_pct,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.NOT_NULL,
                        column_name=col_name,
                        violating_count=null_count,
                        violating_percentage=null_pct,
                        sample_row_indices=sample_indices,
                        details={"null_count": null_count},
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.NOT_NULL,
                        column_name=col_name,
                        severity=rule.severity,
                        message=f"Column '{col_name}' contains {null_count} nulls but allow_null=False",
                        violating_count=null_count,
                        violating_percentage=null_pct,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.NOT_NULL,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

            elif rule.max_null_percentage is not None:
                rule_name = f"column:{col_name}:max_null_percentage"
                passed = null_pct <= rule.max_null_percentage
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    sample_indices = [
                        int(idx) for idx in series[null_mask].index[: self.config.sample_row_limit]
                    ]
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=null_count,
                        violating_percentage=null_pct,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.NOT_NULL,
                        column_name=col_name,
                        violating_count=null_count,
                        violating_percentage=null_pct,
                        sample_row_indices=sample_indices,
                        details={
                            "observed_percentage": null_pct,
                            "threshold_percentage": rule.max_null_percentage,
                        },
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.NOT_NULL,
                        column_name=col_name,
                        severity=rule.severity,
                        message=(
                            f"Column '{col_name}' null percentage {null_pct}% exceeds allowed limit "
                            f"{rule.max_null_percentage}%"
                        ),
                        violating_count=null_count,
                        violating_percentage=null_pct,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.NOT_NULL,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

            # Non-null values for content-level validation
            non_null_series = series.dropna()
            non_null_count = len(non_null_series)

            # 2B. Column Uniqueness Check
            if rule.unique:
                rule_name = f"column:{col_name}:unique"
                dup_mask = non_null_series.duplicated()
                dup_count = int(dup_mask.sum())
                dup_pct = round((dup_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
                passed = dup_count == 0
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    sample_indices = [
                        int(idx) for idx in non_null_series[dup_mask].index[: self.config.sample_row_limit]
                    ]
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=dup_count,
                        violating_percentage=dup_pct,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.UNIQUE,
                        column_name=col_name,
                        violating_count=dup_count,
                        violating_percentage=dup_pct,
                        sample_row_indices=sample_indices,
                        details={"duplicate_value_count": dup_count},
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.UNIQUE,
                        column_name=col_name,
                        severity=rule.severity,
                        message=f"Column '{col_name}' contains {dup_count} duplicate values but unique=True",
                        violating_count=dup_count,
                        violating_percentage=dup_pct,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.UNIQUE,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

            # 2C. Allowed Values Enum Check
            if rule.allowed_values is not None and non_null_count > 0:
                rule_name = f"column:{col_name}:allowed_values"
                allowed_set = set(rule.allowed_values)
                # Compare matching string or exact representations
                violating_mask = ~non_null_series.isin(allowed_set)
                violating_count = int(violating_mask.sum())
                violating_pct = round((violating_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
                passed = violating_count == 0
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    sample_indices = [
                        int(idx)
                        for idx in non_null_series[violating_mask].index[: self.config.sample_row_limit]
                    ]
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.ALLOWED_VALUES,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        sample_row_indices=sample_indices,
                        details={"allowed_set_size": len(allowed_set)},
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.ALLOWED_VALUES,
                        column_name=col_name,
                        severity=rule.severity,
                        message=(
                            f"Column '{col_name}' contains {violating_count} values outside allowed enumeration"
                        ),
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.ALLOWED_VALUES,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

            # 2D. Numeric Range & Malformed Numeric Check
            if (rule.min_value is not None or rule.max_value is not None) and non_null_count > 0:
                rule_name = f"column:{col_name}:numeric_range"
                numeric_converted = pd.to_numeric(non_null_series, errors="coerce")
                malformed_numeric_mask = numeric_converted.isna()
                malformed_count = int(malformed_numeric_mask.sum())

                # Out of range mask on valid numbers
                out_of_range_mask = pd.Series(False, index=non_null_series.index)
                valid_numbers = numeric_converted.dropna()

                if rule.min_value is not None:
                    out_of_range_mask.loc[valid_numbers.index] |= valid_numbers < rule.min_value
                if rule.max_value is not None:
                    out_of_range_mask.loc[valid_numbers.index] |= valid_numbers > rule.max_value

                total_violating_mask = malformed_numeric_mask | out_of_range_mask
                violating_count = int(total_violating_mask.sum())
                violating_pct = round((violating_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
                passed = violating_count == 0
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    sample_indices = [
                        int(idx)
                        for idx in non_null_series[total_violating_mask].index[
                            : self.config.sample_row_limit
                        ]
                    ]
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.NUMERIC_RANGE,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        sample_row_indices=sample_indices,
                        details={
                            "min_bound": rule.min_value,
                            "max_bound": rule.max_value,
                            "malformed_non_numeric_count": malformed_count,
                        },
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.NUMERIC_RANGE,
                        column_name=col_name,
                        severity=rule.severity,
                        message=(
                            f"Column '{col_name}' has {violating_count} values violating numeric range "
                            f"[{rule.min_value}, {rule.max_value}] or non-numeric"
                        ),
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.NUMERIC_RANGE,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

            # 2E. Regex String Format Check
            if rule.regex_pattern and non_null_count > 0:
                rule_name = f"column:{col_name}:regex_format"
                compiled_regex = re.compile(rule.regex_pattern)
                str_series = non_null_series.astype(str)

                # Check pattern matching
                violating_indices: List[int] = []
                for idx, val in str_series.items():
                    if not compiled_regex.search(val):
                        violating_indices.append(int(idx))

                violating_count = len(violating_indices)
                violating_pct = round((violating_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
                passed = violating_count == 0
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    sample_indices = violating_indices[: self.config.sample_row_limit]
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.REGEX_FORMAT,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        sample_row_indices=sample_indices,
                        details={"regex_pattern": rule.regex_pattern},
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.REGEX_FORMAT,
                        column_name=col_name,
                        severity=rule.severity,
                        message=(
                            f"Column '{col_name}' contains {violating_count} values failing regex format"
                        ),
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.REGEX_FORMAT,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

            # 2F. Date / Datetime Format Check
            if rule.date_format and non_null_count > 0:
                rule_name = f"column:{col_name}:date_format"
                str_series = non_null_series.astype(str)
                violating_indices: List[int] = []

                for idx, val in str_series.items():
                    val_str = val.strip()
                    try:
                        if rule.date_format.upper() == "ISO8601":
                            # ISO-8601 format attempt
                            pd.to_datetime(val_str, format="ISO8601")
                        else:
                            datetime.strptime(val_str, rule.date_format)
                    except Exception:
                        violating_indices.append(int(idx))

                violating_count = len(violating_indices)
                violating_pct = round((violating_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
                passed = violating_count == 0
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    sample_indices = violating_indices[: self.config.sample_row_limit]
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.DATE_FORMAT,
                        column_name=col_name,
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        sample_row_indices=sample_indices,
                        details={"expected_date_format": rule.date_format},
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.DATE_FORMAT,
                        column_name=col_name,
                        severity=rule.severity,
                        message=(
                            f"Column '{col_name}' contains {violating_count} values failing date format "
                            f"'{rule.date_format}'"
                        ),
                        violating_count=violating_count,
                        violating_percentage=violating_pct,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.DATE_FORMAT,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

            # 2G. Expected Dtype Check
            if rule.expected_dtype:
                rule_name = f"column:{col_name}:expected_dtype"
                inferred_type = DatasetProfiler._map_dtype(series.dtype)
                passed = inferred_type == rule.expected_dtype.lower()
                issue = None
                if not passed:
                    affected_columns_set.add(col_name)
                    evidence_hash = generate_quality_evidence_hash(
                        dataset_id=dataset_id,
                        version_number=version_number,
                        rule_name=rule_name,
                        column_name=col_name,
                        violating_count=total_rows,
                        violating_percentage=100.0,
                    )
                    evidence_ref = EvidenceReference(
                        rule_name=rule_name,
                        rule_type=RuleType.EXPECTED_DTYPE,
                        column_name=col_name,
                        violating_count=total_rows,
                        violating_percentage=100.0,
                        details={
                            "expected_dtype": rule.expected_dtype,
                            "inferred_dtype": inferred_type,
                        },
                        evidence_hash=evidence_hash,
                    )
                    issue = QualityIssue(
                        rule_name=rule_name,
                        rule_type=RuleType.EXPECTED_DTYPE,
                        column_name=col_name,
                        severity=rule.severity,
                        message=(
                            f"Column '{col_name}' data type mismatch: expected '{rule.expected_dtype}', "
                            f"found '{inferred_type}'"
                        ),
                        violating_count=total_rows,
                        violating_percentage=100.0,
                        evidence_ref=evidence_ref,
                    )
                    issues.append(issue)

                rule_results.append(
                    QualityRuleResult(
                        rule_name=rule_name,
                        rule_type=RuleType.EXPECTED_DTYPE,
                        column_name=col_name,
                        passed=passed,
                        severity=rule.severity,
                        issue=issue,
                    )
                )

        # -------------------------------------------------------------
        # 3. Aggregate Summary & Scoring
        # -------------------------------------------------------------
        total_rules = len(rule_results)
        passed_rules = sum(1 for r in rule_results if r.passed)
        failed_rules = total_rules - passed_rules
        quality_score = round((passed_rules / total_rules) * 100, 2) if total_rules > 0 else 100.0

        has_critical = any(issue.severity == QualitySeverity.CRITICAL for issue in issues)
        has_high = any(issue.severity == QualitySeverity.HIGH for issue in issues)

        summary = QualitySummary(
            dataset_id=dataset_id,
            version_number=version_number,
            inspection_run_id=run_id,
            total_rows=total_rows,
            total_columns=total_columns,
            total_rules_evaluated=total_rules,
            passed_rules_count=passed_rules,
            failed_rules_count=failed_rules,
            quality_score=quality_score,
            has_critical_failures=has_critical,
            has_high_failures=has_high,
            affected_columns=sorted(list(affected_columns_set)),
            evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
        )

        return QualityReport(
            dataset_id=dataset_id,
            version_number=version_number,
            inspection_run_id=run_id,
            summary=summary,
            rule_results=rule_results,
            issues=issues,
        )

    def validate_dataset_bytes(
        self,
        content: bytes,
        file_format: str,
        dataset_id: str,
        version_number: int = 1,
        inspection_run_id: Optional[str] = None,
    ) -> QualityReport:
        """
        Safely profile and validate raw dataset bytes in memory.
        """
        try:
            df = DatasetProfiler.load_dataframe(content, file_format)
        except ProfilingError as exc:
            raise InvalidDatasetForValidation(
                f"Failed to parse dataset bytes for quality validation: {str(exc)}"
            ) from exc

        return self.validate_dataframe(
            df=df,
            dataset_id=dataset_id,
            version_number=version_number,
            inspection_run_id=inspection_run_id,
        )
