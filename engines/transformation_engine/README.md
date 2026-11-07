# ReleaseGate Safe Dataset Transformation Engine

The **Safe Dataset Transformation Engine** (`engines/transformation_engine/`) enables controlled, risk-mitigating data transformations within the **ReleaseGate Local Processing Plane (Environment B)**.

It provides declarative sanitization techniques (masking, pseudonymization, generalization, column pruning, and row filtering) while strictly prohibiting model-generated arbitrary code, eval/exec strings, SQL statements, or shell commands.

---

## 1. Architectural Principles & Security Boundaries

```
+-------------------------------------------------------------------------+
|                  LOCAL DATA PROCESSING PLANE (Environment B)             |
|                                                                         |
|  [Original Dataset (Immutable v1)]                                      |
|            |                                                            |
|            | (Deep Copy / Non-Destructive Read)                         |
|            v                                                            |
|   +-------------------------------------------------------------+       |
|   |                  TransformationEngine                       |       |
|   |  - Schema & Security Injection Validator                    |       |
|   |  - Allowlisted Declarative Operations                       |       |
|   |  - Deterministic HMAC-SHA256 Pseudonymization               |       |
|   |  - Masking, Generalization, Filtering Primitives            |       |
|   +-------------------------------------------------------------+       |
|            |                                                            |
|            +------------------------------------+                       |
|            v                                    v                       |
|  [Transformed Dataset (v2)]          [TransformationResult]             |
|  - Stored as new immutable artifact  - Provenance (input/output hashes) |
|  - Cryptographic output SHA-256      - Aggregate preview (0 raw values) |
|  * Original v1 remains 100% UNCHANGED- Automated re-validation reports  |
+-------------------------------------------------------------------------+
                                                  |
                                                  | .to_cloud_metadata()
                                                  v
+-------------------------------------------------------------------------+
|                   CLOUD CONTROL PLANE (Environment A)                   |
|                                                                         |
|  Inspection & Lineage Ledger (Metadata Coordination Only)               |
+-------------------------------------------------------------------------+
```

### Core Security Guarantees:
1. **Source Immutability**: Source datasets are never overwritten, in-place mutated, or modified. Every transformation creates a new, immutable dataset version with its own cryptographic SHA-256 hash.
2. **Rejection of Arbitrary Executable Code**: The engine accepts only structured, typed Pydantic specifications. Strings containing `eval`, `exec`, `__import__`, `os.system`, `subprocess`, SQL statements, or shell escapes are rejected before execution.
3. **Safe Aggregate Previews**: Preview statistics capture row/column deltas, affected counts, and operation summaries without exposing raw sensitive strings.
4. **Mandatory Post-Transformation Re-Verification**: Transformations do not assume safety. Post-transformation privacy (PII), data quality, and release policy evaluations are immediately re-executed to score the candidate release.

---

## 2. Allowlisted Transformation Operations

| Operation (`op_type`) | Description | Supported Parameters |
| :--- | :--- | :--- |
| **`REMOVE_COLUMN`** | Drops one or more sensitive or unneeded columns. | `column_name` |
| **`MASK_COLUMN`** | Redacts content using standardized masking strategies. | `column_name`, `strategy` (`FULL_REDACTION`, `PARTIAL_EMAIL`, `PARTIAL_PHONE`, `LAST_4_VISIBLE`, `CUSTOM_PLACEHOLDER`), `placeholder` |
| **`PSEUDONYMIZE_COLUMN`** | Keyed deterministic HMAC-SHA256 tokenization. Consistent across datasets when using the same salt. | `column_name`, `salt`, `prefix` (default: `"PSEUDO_"`) |
| **`GENERALIZE_COLUMN`** | Coarsens high-precision data into lower-risk buckets. | `column_name`, `strategy` (`NUMERIC_BINNING`, `DATE_TRUNCATION`, `CATEGORY_BUCKETING`), `bins`, `bin_labels`, `date_interval` (`YEAR`, `MONTH`, `DECADE`), `category_mapping` |
| **`FILTER_ROWS`** | Declarative row filtering using safe comparison operators. | `column_name`, `operator` (`EQUALS`, `NOT_EQUALS`, `GREATER_THAN`, `IN_LIST`, `IS_NULL`, etc.), `value`, `values_list` |

---

## 3. Usage Example

```python
import pandas as pd
from engines.transformation_engine import (
    TransformationEngine,
    TransformationSpec,
    RemoveColumnOp,
    MaskColumnOp,
    MaskingStrategy,
    PseudonymizeColumnOp,
    GeneralizeColumnOp,
    GeneralizationStrategy,
    FilterRowsOp,
    FilterOperator,
)

# 1. Define declarative transformation pipeline
spec = TransformationSpec(
    spec_id="sanitize-customer-v1",
    operations=[
        # Drop high-risk identifiers
        RemoveColumnOp(column_name="ssn"),
        # Mask emails (e.g. j***e@example.com)
        MaskColumnOp(column_name="email", strategy=MaskingStrategy.PARTIAL_EMAIL),
        # Deterministically pseudonymize customer IDs
        PseudonymizeColumnOp(column_name="customer_id", salt="enterprise_salt_2026"),
        # Coarsen age into demographic bins
        GeneralizeColumnOp(
            column_name="age",
            strategy=GeneralizationStrategy.NUMERIC_BINNING,
            bins=[0, 18, 30, 50, 100],
            bin_labels=["<18", "18-29", "30-49", "50+"],
        ),
        # Retain only active records
        FilterRowsOp(column_name="status", operator=FilterOperator.EQUALS, value="ACTIVE"),
    ]
)

# 2. Execute transformation on raw bytes with automatic post-revalidation
with open("raw_dataset_v1.csv", "rb") as f:
    raw_bytes = f.read()

result = TransformationEngine.transform_dataset_bytes(
    content=raw_bytes,
    file_format="csv",
    spec=spec,
    dataset_id="9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    input_version=1,
    output_version=2,
    run_post_verification=True,
)

print(f"Input Hash:  {result.input_hash}")
print(f"Output Hash: {result.output_hash}")
print(f"Post-Transformation Policy Status: {result.post_policy_evaluation['status']}")
```

---

## 4. Anti-Hallucination & Governance Disclaimers

> **Safety Invariant**:
> Applying a transformation **does not automatically make a dataset safe for release**. The transformed dataset must be re-profiled, re-scanned for privacy, re-validated for quality, and re-evaluated by the Release Policy Engine before submission to the independent reviewer and human steward authorization queue.
