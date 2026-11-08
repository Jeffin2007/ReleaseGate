# ReleaseGate Deterministic Data Quality Validator Engine

The **Deterministic Data Quality Validator Engine** (`engines/quality_validator/`) provides reproducible, audit-grade dataset quality inspection for the **ReleaseGate Local Processing Plane (Environment B)**.

It evaluates tabular datasets using deterministic, rule-based algorithms. All raw values and violation records are maintained strictly on the local machine, emitting only aggregate metrics, coordinates, and SHA-256 evidence fingerprints to the Cloud Control Plane.

---

## 1. Architectural Boundaries & Guarantees

```
+-------------------------------------------------------------------------+
|                  LOCAL DATA PROCESSING PLANE (Environment B)             |
|                                                                         |
|  [Raw Dataset File / Stream / In-Memory Artifact]                       |
|            |                                                            |
|            v                                                            |
|   +-------------------------------------------------------------+       |
|   |                      QualityValidator                       |       |
|   |  - Nullability & Missing Value Checks                       |       |
|   |  - Duplicate Record & Uniqueness Verification               |       |
|   |  - Bounded Numeric Range Validation                         |       |
|   |  - Allowed-Values Enumeration Constraints                   |       |
|   |  - Date Format & Regex Pattern Verification                 |       |
|   |  - Inconsistent Dtype Detection                             |       |
|   +-------------------------------------------------------------+       |
|            |                                                            |
|            v                                                            |
|   [QualityReport]                                                       |
|   - Aggregate scores & rule pass/fail rates                             |
|   - Affected column rosters & severity levels                           |
|   - Violating counts & violation percentages                            |
|   - Opaque SHA-256 evidence fingerprints                                |
|   - Bounded row coordinates (for local audit only)                      |
|   * ZERO raw violating cell values                                      |
+-------------------------------------------------------------------------+
                                     |
                                     | .to_cloud_metadata() (Sanitized ONLY)
                                     v
+-------------------------------------------------------------------------+
|                   CLOUD CONTROL PLANE (Environment A)                   |
|                                                                         |
|  POST /api/v1/datasets/register-metadata (Metadata Coordination Only)   |
+-------------------------------------------------------------------------+
```

### Core Security & Reproducibility Principles:
1. **Zero Raw Value Leakage**: Reports, issue objects, and outbound metadata never contain violating cell text or unredacted raw data.
2. **Deterministic & Repeatable**: Given the identical dataset and configuration, repeated runs produce 100% identical pass/fail evaluations, issue counts, and SHA-256 evidence fingerprints.
3. **No AI Hallucinations**: Rule evaluations are purely deterministic code executions without statistical drift or LLM guesswork.
4. **Non-Destructive**: The validator strictly inspects dataset bytes without modifying original source files or stored artifacts.

---

## 2. Supported Validation Rules

### Dataset-Level Rules (`DatasetLevelRules`)
- `no_duplicate_rows` (`bool`, default `True`): Identifies identical duplicate rows across the entire dataset.
- `max_total_null_percentage` (`float`, optional): Sets a threshold for the total proportion of null cells across all columns.
- `required_columns` (`List[str]`, optional): Validates that mandatory column headers exist in the dataset schema.

### Column-Level Rules (`ColumnRule`)
- **Nullability**: `allow_null=False` forbids any missing values; `max_null_percentage=5.0` allows up to 5% nulls.
- **Uniqueness**: `unique=True` verifies that all non-null values in the column are distinct.
- **Allowed Values**: `allowed_values=["ACTIVE", "INACTIVE"]` verifies that values belong to an approved enumeration.
- **Numeric Ranges**: `min_value=0.0`, `max_value=120.0` validates numeric bounds and flags malformed non-numeric values.
- **Regex Patterns**: `regex_pattern=r"^[A-Z]{3}-\d{4}$"` enforces string structure.
- **Date Formats**: `date_format="%Y-%m-%d"` or `date_format="ISO8601"` verifies that date strings can be parsed according to the specified pattern.
- **Expected Data Types**: `expected_dtype="integer"` ensures the column matches the expected semantic type.

---

## 3. Configuration & Usage Examples

### Python API Example

```python
import pandas as pd
from engines.quality_validator import (
    QualityValidator,
    QualityValidationConfig,
    DatasetLevelRules,
    ColumnRule,
    QualitySeverity,
)

# 1. Define quality constraints
config = QualityValidationConfig(
    dataset_rules=DatasetLevelRules(
        no_duplicate_rows=True,
        required_columns=["customer_id", "email", "amount", "status"],
    ),
    column_rules=[
        ColumnRule(
            column_name="customer_id",
            unique=True,
            allow_null=False,
            severity=QualitySeverity.CRITICAL,
        ),
        ColumnRule(
            column_name="amount",
            min_value=0.01,
            max_value=1000000.0,
            severity=QualitySeverity.HIGH,
        ),
        ColumnRule(
            column_name="status",
            allowed_values=["PENDING", "COMPLETED", "CANCELLED"],
            severity=QualitySeverity.HIGH,
        ),
        ColumnRule(
            column_name="signup_date",
            date_format="%Y-%m-%d",
            severity=QualitySeverity.MEDIUM,
        ),
    ],
)

# 2. Run deterministic validation
validator = QualityValidator(config=config)
df = pd.read_csv("transactions.csv")

report = validator.validate_dataframe(
    df=df,
    dataset_id="9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    version_number=1,
)

# 3. Inspect results
print(f"Quality Score: {report.summary.quality_score}%")
print(f"Passed: {report.summary.passed_rules_count}/{report.summary.total_rules_evaluated}")
print(f"Affected Columns: {report.summary.affected_columns}")

# 4. Generate sanitized cloud payload
cloud_payload = report.to_cloud_metadata()
```

---

## 4. Local Worker Integration

In the Local Ingestion Worker:

```python
from local_worker.ingestion_service import LocalIngestionWorker

worker = LocalIngestionWorker()
quality_metadata = worker.validate_quality_for_artifact(
    artifact_ref=payload.local_artifact_ref,
    dataset_id=dataset_id,
    version_number=1,
    quality_config=config,
)
```
