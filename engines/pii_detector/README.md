# ReleaseGate Local Privacy and PII Detection Engine

The **Local Privacy and PII Detection Engine** (`engines/pii_detector/`) provides deterministic, privacy-preserving sensitive information detection for datasets within the **ReleaseGate Local Processing Plane (Environment B)**.

It integrates Microsoft Presidio Analyzer with architectural controls that guarantee raw dataset bytes, matched sensitive substrings, and unredacted values are processed **strictly on the local machine** and are **never exposed** to the Cloud Control Plane or written to ordinary application logs.

---

## 1. Architectural Boundary & Privacy Guarantees

```
+-------------------------------------------------------------------------+
|                  LOCAL DATA PROCESSING PLANE (Environment B)             |
|                                                                         |
|  [Raw Dataset File/Stream]                                              |
|            |                                                            |
|            v                                                            |
|   +-------------------+                                                 |
|   |   PIIDetector     |                                                 |
|   |  - Presidio NER   |                                                 |
|   |  - Regex Engines  |                                                 |
|   |  - Custom Rules   |                                                 |
|   +-------------------+                                                 |
|            |                                                            |
|            v                                                            |
|   [PIIDetectionReport]                                                  |
|   - Column names                                                        |
|   - Entity types & counts                                               |
|   - Statistical confidence                                              |
|   - Severity classifications                                            |
|   - Opaque SHA-256 evidence hashes                                      |
|   * ZERO raw text values                                                |
+-------------------------------------------------------------------------+
                                     |
                                     | .to_cloud_metadata() (Sanitized ONLY)
                                     v
+-------------------------------------------------------------------------+
|                   CLOUD CONTROL PLANE (Environment A)                   |
|                                                                         |
|  FastAPI Metadata Registration & ReleaseGate Governance Policies        |
+-------------------------------------------------------------------------+
```

### Key Security Controls:
1. **Zero Raw Value Leakage**: `PIIFinding` and `EvidenceReference` records retain occurrence counts, length distributions, confidence ranges, sample row indices (bounded for local audit), and SHA-256 evidence hashes. They **never** retain or transmit detected values.
2. **Deterministic Local Execution**: Scanning operates in-memory on local pandas DataFrames or byte streams. No external network requests or third-party cloud LLM endpoints are invoked for deterministic PII scanning.
3. **Structured Cloud Serialization**: The `.to_cloud_metadata()` method generates a sanitized metadata dictionary safe for outbound synchronization to the ReleaseGate Cloud Control Plane.

---

## 2. Supported Entity Types & Severity Matrix

The detector categorizes identified entities into structured severity tiers:

| Severity Level | Supported Entity Types | Description / Impact |
| :--- | :--- | :--- |
| **CRITICAL** | `US_SSN`, `CREDIT_CARD`, `US_PASSPORT`, `UK_NHS`, `MEDICAL_LICENSE` | High-impact government identifiers and financial instruments requiring immediate blocking or gating. |
| **HIGH** | `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `US_DRIVER_LICENSE`, `US_BANK_NUMBER`, `IBAN_CODE`, `CRYPTO`, `INTERNAL_EMPLOYEE_ID`* | Direct personal identifiers and financial account numbers. |
| **MEDIUM** | `LOCATION`, `IP_ADDRESS`, `ORGANIZATION` | Quasi-identifiers, geographical coordinates, and network identifiers. |
| **LOW** | `DATE_TIME`, `URL`, `NRP` | Low-risk metadata, non-sensitive dates, or public links. |
| **INFORMATIONAL**| Configurable custom tags | Custom flags or informational organizational markers. |

*\* Custom recognizers inherit configurable severity (defaults to HIGH).*

---

## 3. Language Models & Installation Guide

Presidio Analyzer utilizes spaCy for Named Entity Recognition (NER), particularly for entities such as `PERSON`, `LOCATION`, and `ORGANIZATION`. Pattern-based recognizers (`EMAIL_ADDRESS`, `PHONE_NUMBER`, `IP_ADDRESS`, `CREDIT_CARD`, `US_SSN`, and custom patterns) do not require heavy transformer models.

### Recommended Model Installation

To enable full NER capabilities:

```bash
# 1. Install presidio-analyzer and spacy dependencies
pip install presidio-analyzer>=2.2.365 spacy>=3.8.0

# 2. Download the lightweight English language model (en_core_web_sm)
python -m spacy download en_core_web_sm
```

### Explicit Fallback & Unavailable Model Behavior

The engine is engineered to handle missing models without crashing:

- **When `allow_nlp_fallback=True` (default)**:
  If `en_core_web_sm` is missing or fails to load, `PIIDetector` automatically initializes Presidio's `NoOpNlpEngine`.
  - Pattern recognizers (email, phone, credit cards, IP addresses, SSNs, and custom regexes) continue scanning seamlessly.
  - The report records `nlp_engine="pattern_fallback:noop"` in its metadata summary.
- **When `allow_nlp_fallback=False` (strict mode)**:
  `PIIDetector` immediately raises `LanguageModelUnavailableError` if the specified model is missing, or `UnsupportedLanguageError` if an unsupported language code is provided.

---

## 4. Configuration & Custom Recognizers

The detector supports runtime configuration via `PIIDetectorConfig`.

### Adding Custom Pattern Recognizers

Organizations can register internal identifier patterns (such as employee numbers, project tokens, or customer ID numbers):

```python
from engines.pii_detector import (
    PIIDetector,
    PIIDetectorConfig,
    CustomPatternRecognizerConfig,
    PIISeverity,
)

# 1. Define custom employee ID recognizer (e.g., EMP-US-1234)
employee_id_rec = CustomPatternRecognizerConfig(
    name="internal_emp_id",
    supported_entity="INTERNAL_EMPLOYEE_ID",
    patterns=[{
        "name": "emp_badge_regex",
        "regex": r"\bEMP-[A-Z]{2}-\d{4}\b",
        "score": 0.95,
    }],
    context=["employee", "badge", "staff", "id"],
    severity=PIISeverity.HIGH,
)

# 2. Instantiate detector with configuration and severity overrides
config = PIIDetectorConfig(
    confidence_threshold=0.45,
    custom_recognizers=[employee_id_rec],
    severity_overrides={"IP_ADDRESS": PIISeverity.CRITICAL},
    max_rows_to_sample=1000, # Optional row sampling bound
)

detector = PIIDetector(config=config)
```

---

## 5. Usage Examples

### Scanning a Pandas DataFrame

```python
import pandas as pd
from engines.pii_detector import PIIDetector

detector = PIIDetector()

df = pd.read_csv("local_customer_data.csv")
report = detector.scan_dataframe(
    df=df,
    dataset_id="9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    version_number=1,
)

print(f"Scanned {report.summary.total_rows_scanned} rows across {report.summary.total_columns_scanned} columns.")
print(f"High PII Found: {report.has_high_pii}, Critical PII Found: {report.has_critical_pii}")

for finding in report.findings:
    print(f"[{finding.severity}] {finding.column_name} -> {finding.entity_type} ({finding.occurrence_count} matches)")

# Export sanitized metadata for Cloud Control Plane
cloud_payload = report.to_cloud_metadata()
```

### Scanning In-Memory File Bytes

```python
with open("dataset.csv", "rb") as f:
    raw_bytes = f.read()

report = detector.scan_dataset_bytes(
    content=raw_bytes,
    file_format="csv",
    dataset_id="dataset-uuid",
    version_number=1,
)
```

---

## 6. Regulatory & Coverage Disclaimer

> **Anti-Hallucination & Governance Notice**:
> This automated deterministic scan is powered by rule-based patterns and statistical local Named Entity Recognition. It **does not claim complete, exhaustive, or 100% detection** of all sensitive information or proprietary trade secrets. It is designed as an architectural release gate and risk signal, not a substitute for comprehensive data compliance audits.
