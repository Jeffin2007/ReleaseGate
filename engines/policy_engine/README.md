# ReleaseGate Deterministic Release Policy & Risk Engine

The **Release Policy & Risk Engine** (`engines/policy_engine/`) evaluates dataset release readiness using explicit, versioned governance policies and the **Frozen 100-Point Weighted Risk Scoring System** defined in the ReleaseGate Frozen Architecture Baseline v1.0.

All evaluations are 100% deterministic, reproducible, and executed locally without statistical drift or LLM guesswork.

---

## 1. Frozen 100-Point Risk Scoring Matrix

The risk engine evaluates datasets across five explicit weighted categories totaling 100 points:

| # | Evaluation Category | Maximum Points | Risk Weight | Key Evaluation Criteria |
| :-: | :--- | :-: | :-: | :--- |
| **1** | **Sensitive Information (PII)** | **35 pts** | **35%** | Presidio PII detections, identity credentials, direct identifiers (`PERSON`, `EMAIL`, `PHONE`), and financial markers. |
| **2** | **Data Quality** | **20 pts** | **20%** | Null distributions, duplicate records, format validation, numeric range bounds, and schema integrity. |
| **3** | **Licensing & Provenance** | **20 pts** | **20%** | Approved commercial/open licenses, forbidden copyleft licenses (`GPL`, `AGPL`), and verifiable origin citations. |
| **4** | **Metadata Completeness** | **10 pts** | **10%** | Mandatory fields (`dataset_name`, `content_hash`, `file_format`, `file_size`) and descriptive tags. |
| **5** | **Policy Violations** | **15 pts** | **15%** | Prohibited regulatory domains (`biometrics`, `defense`), retention schedules, and export restrictions. |
| **Total** | **Comprehensive Risk Score** | **100 pts** | **100%** | **Aggregate Weighted Risk Score** |

---

## 2. Risk Bands & Release Eligibility

Aggregate scores map into four standard risk bands:

| Risk Band | Score Range | Release Decision | Description |
| :--- | :---: | :---: | :--- |
| **LOW** | **0 – 19** | **PASSED** | Clean dataset with minimal or zero risk indicators. Eligible for automated human steward sign-off. |
| **MODERATE** | **20 – 39** | **WARNING** | Moderate risk indicators. Release eligible only with explicit dual human authorization. |
| **HIGH** | **40 – 69** | **BLOCKED** | Significant risk findings. Ineligible for release until remediation (masking, redaction, filtering) is applied. |
| **CRITICAL** | **70 – 100** | **BLOCKED** | Extreme privacy, quality, or compliance risks. Publication strictly prohibited. |

---

## 3. Critical Policy Violation Override (Hard Block)

> **Core Invariant**: A critical policy violation triggers a hard **BLOCKED** release decision **regardless of the aggregate score**. A low total risk score CANNOT override a critical policy violation.

### Hard Blocking Conditions:
1. **Critical PII**: Unredacted `US_SSN`, `CREDIT_CARD`, `US_PASSPORT`, or `UK_NHS` numbers detected.
2. **Forbidden Licenses**: Datasets marked with `GPL-2.0`, `GPL-3.0`, `AGPL-3.0`, `PROPRIETARY_UNLICENSED`, or `UNKNOWN`.
3. **Prohibited Regulatory Domains**: Datasets flagged with prohibited tags such as `biometrics_unconsented` or `underage_surveillance`.
4. **Missing Mandatory Evidence**: Datasets missing PII inspection evidence, quality validation reports, or required metadata (Fail-Closed Security).

When a critical violation occurs:
- `is_release_eligible` is set to `False`.
- `status` is set to `EvaluationStatus.BLOCKED`.
- `critical_override_applied` is set to `True`.
- Specific blocking reasons are logged in `blocking_reasons`.

---

## 4. Versioned Policy Configuration

Policies are stored as immutable, version-bound configurations. ReleaseGate ships with baseline version `1.0.0` located at `engines/policy_engine/policies/baseline_policy_v1.0.json`.

```json
{
  "policy_id": "releasegate-baseline-v1",
  "policy_name": "Frozen Architecture Baseline Policy",
  "policy_version": "1.0.0",
  "max_acceptable_score": 39.99,
  "sensitive_info": { "max_points": 35.0, "block_on_critical_pii": true },
  "data_quality": { "max_points": 20.0, "block_on_critical_quality_issues": true },
  "licensing_provenance": { "max_points": 20.0, "block_on_forbidden_license": true },
  "metadata_completeness": { "max_points": 10.0, "block_on_missing_required_fields": true },
  "policy_violations": { "max_points": 15.0, "block_on_prohibited_domain": true }
}
```

---

## 5. Usage Example

```python
from engines.policy_engine import PolicyEngine

engine = PolicyEngine()

result = engine.evaluate(
    dataset_id="9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    version_number=1,
    pii_report=pii_report,
    quality_report=quality_report,
    metadata=metadata,
    provenance=provenance,
    context=context,
)

print(f"Risk Score: {result.score_breakdown.total_risk_score} / 100")
print(f"Risk Band: {result.score_breakdown.risk_band.value}")
print(f"Release Eligible: {result.is_release_eligible}")
print(f"Status: {result.status.value}")

if result.blocking_reasons:
    print("Blocking Reasons:", result.blocking_reasons)

# Export sanitized cloud metadata
cloud_payload = result.to_cloud_metadata()
```

---

## 6. Regulatory & Compliance Notice

> **Non-Legal Disclaimer**:
> This automated risk scoring engine executes internal, organizational release policies and heuristics. Risk scores, bands, and eligibility determinations **do not constitute legal compliance guarantees, regulatory approvals, or statutory certifications** (such as GDPR, HIPAA, or CCPA compliance). They serve solely as deterministic internal safety gates within the ReleaseGate governance workflow.
