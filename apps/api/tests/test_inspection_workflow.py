"""
Comprehensive automated test suite for the Complete Dataset Inspection Workflow (Prompt 10).
Verifies:
- Deterministic profiling, Presidio privacy detection, quality validation, and policy risk evaluation.
- Synthesis of granular, sanitized Findings and Auditable Summary Reports.
- Hard blocking overrides for critical policy violations.
- Reproducibility across repeated runs.
- Execution against locally stored artifact references.
- Cloud Control Plane persistence and REST API endpoints.
- Strict ZERO raw sensitive value leakage guarantee.
"""

import hashlib
import json
from pathlib import Path
import tempfile
import uuid
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.db.models.inspection import FindingType, InspectionStatus, InspectionType
from app.schemas.dataset import (
    DatasetMetadataRegistrationRequest,
    DatasetProfileSchema,
)
from engines.pii_detector import PIIDetectorConfig
from engines.quality_validator import ColumnRule, DatasetLevelRules, QualityValidationConfig
from engines.policy_engine import PolicyConfig
from local_worker.cloud_client import CloudControlPlaneClient
from local_worker.ingestion_service import LocalIngestionWorker
from local_worker.inspection_pipeline import (
    AuditableInspectionResult,
    DatasetInspectionWorkflow,
    InspectionWorkflowError,
)
from local_worker.secure_storage import LocalDatasetStorage


def test_end_to_end_clean_dataset_inspection():
    """
    Test complete inspection workflow on a clean dataset with no sensitive PII
    and zero quality violations. Verifies low risk score, LOW risk band, and release eligibility.
    """
    workflow = DatasetInspectionWorkflow()

    clean_csv = (
        "product_id,product_name,category,price,inventory_count\n"
        "101,Standard Widget,Hardware,19.99,150\n"
        "102,Deluxe Gadget,Electronics,49.99,75\n"
        "103,Basic Cable,Electronics,9.50,300\n"
        "104,Heavy Duty Bolt,Hardware,1.25,500\n"
    ).encode("utf-8")

    dataset_id = uuid.uuid4()
    version_id = uuid.uuid4()

    result: AuditableInspectionResult = workflow.execute_inspection(
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        version_number=1,
        content=clean_csv,
        file_format="csv",
        provenance={"has_license": True, "is_approved": True, "license_type": "MIT", "has_author": True},
        context={"domain": "internal_analytics", "has_retention_policy": True},
    )

    assert result.dataset_id == dataset_id
    assert result.dataset_version_id == version_id
    assert result.status == InspectionStatus.COMPLETED
    assert result.inspection_type == InspectionType.FULL_SCAN
    assert result.risk_score <= 19.0, f"Expected Low risk score <= 19, got {result.risk_score}"
    assert result.risk_band == "LOW"
    assert result.is_release_eligible is True
    assert len(result.findings) == 0

    # Summary report validation
    summary = result.summary_report
    assert summary["risk_assessment"]["is_release_eligible"] is True
    assert summary["profiling"]["row_count"] == 4
    assert summary["profiling"]["column_count"] == 5
    assert summary["privacy_inspection"]["total_findings"] == 0
    assert summary["privacy_inspection"]["has_critical_pii"] is False
    assert summary["quality_inspection"]["failed_rules_count"] == 0


def test_end_to_end_pii_detection_inspection():
    """
    Test complete inspection workflow on a dataset with PII (email, phone, person).
    Verifies Presidio detection, granular findings generation, risk score calculation,
    and ZERO raw text leakage.
    """
    workflow = DatasetInspectionWorkflow()

    pii_csv = (
        "emp_id,full_name,work_email,contact_phone,department\n"
        "1,Alice Smith,alice.smith@example.com,202-555-0143,Engineering\n"
        "2,Bob Jones,bob.jones@example.co.uk,415-555-0188,Marketing\n"
        "3,Charlie Brown,charlie.brown@example.org,212-555-0199,Finance\n"
    ).encode("utf-8")

    dataset_id = uuid.uuid4()
    version_id = uuid.uuid4()

    result = workflow.execute_inspection(
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        version_number=1,
        content=pii_csv,
        file_format="csv",
        provenance={"has_license": True, "license_type": "Apache-2.0"},
    )

    assert result.status == InspectionStatus.COMPLETED
    assert len(result.findings) >= 2

    # Check for PII findings
    pii_findings = [f for f in result.findings if f.finding_type == FindingType.PII]
    categories = {f.category for f in pii_findings}
    assert "EMAIL_ADDRESS" in categories or "PHONE_NUMBER" in categories

    # Verify sensitive information score contributed to total risk
    risk_assessment = result.summary_report["risk_assessment"]
    assert risk_assessment["category_scores"]["sensitive_information"] > 0
    assert result.risk_score >= 10.0

    # Verify evidence references contain zero raw strings
    for f in pii_findings:
        evidence = f.evidence_ref
        assert "evidence_hash" in evidence
        assert "matched_count" in evidence
        assert f.severity in ("HIGH", "MEDIUM", "LOW", "CRITICAL")
        # Ensure email or phone text is NOT in evidence
        evidence_str = json.dumps(evidence)
        assert "@example.com" not in evidence_str
        assert "202-555" not in evidence_str


def test_end_to_end_quality_validation_inspection():
    """
    Test complete inspection workflow on a dataset with missing values and duplicates.
    Verifies quality validator identifies failures and maps them to granular findings.
    """
    # Configure custom quality rules requiring uniqueness and non-null values
    quality_cfg = QualityValidationConfig(
        dataset_level=DatasetLevelRules(allow_duplicate_records=False),
        column_rules=[
            ColumnRule(column_name="account_id", allow_nulls=False, require_unique=True),
            ColumnRule(column_name="score", min_value=0.0, max_value=100.0),
        ],
    )
    workflow = DatasetInspectionWorkflow(quality_config=quality_cfg)

    dirty_csv = (
        "account_id,score,status\n"
        "1001,85.5,ACTIVE\n"
        "1002,,ACTIVE\n"             # Null in required score
        "1001,85.5,ACTIVE\n"         # Duplicate record
        "1003,150.0,SUSPENDED\n"     # Out of range (>100.0)
    ).encode("utf-8")

    dataset_id = uuid.uuid4()
    version_id = uuid.uuid4()

    result = workflow.execute_inspection(
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        version_number=1,
        content=dirty_csv,
        file_format="csv",
    )

    assert result.status == InspectionStatus.COMPLETED
    quality_findings = [f for f in result.findings if f.finding_type == FindingType.QUALITY]
    assert len(quality_findings) >= 1

    # Check quality summary in report
    q_summary = result.summary_report["quality_inspection"]
    assert q_summary["failed_rules_count"] >= 1


def test_end_to_end_critical_policy_override_blocks_release():
    """
    Test that critical policy violations (such as credit card numbers or prohibited domain)
    trigger an immediate automated release block regardless of score.
    """
    workflow = DatasetInspectionWorkflow()

    # Dataset with credit card numbers (CRITICAL PII)
    critical_csv = (
        "transaction_id,user_id,card_number,amount\n"
        "T1,U1,4532015012345678,120.00\n"
        "T2,U2,4532015098765432,45.50\n"
    ).encode("utf-8")

    dataset_id = uuid.uuid4()
    version_id = uuid.uuid4()

    result = workflow.execute_inspection(
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        version_number=1,
        content=critical_csv,
        file_format="csv",
        context={"domain": "classified_defense"},  # Critical policy violation: prohibited domain
    )

    assert result.is_release_eligible is False
    assert len(result.summary_report["risk_assessment"]["blocking_reasons"]) >= 1


def test_inspection_workflow_reproducibility():
    """
    Verify that identical dataset inputs produce identical risk scores,
    risk bands, finding counts, and evidence hashes across independent runs.
    """
    workflow = DatasetInspectionWorkflow()

    csv_data = (
        "user_id,email,age,city\n"
        "1,user1@test.com,25,Seattle\n"
        "2,user2@test.com,30,Austin\n"
        "3,,40,Boston\n"
    ).encode("utf-8")

    dataset_id = uuid.uuid4()
    version_id = uuid.uuid4()

    run1 = workflow.execute_inspection(
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        version_number=1,
        content=csv_data,
        file_format="csv",
    )

    run2 = workflow.execute_inspection(
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        version_number=1,
        content=csv_data,
        file_format="csv",
    )

    assert run1.risk_score == run2.risk_score
    assert run1.risk_band == run2.risk_band
    assert run1.is_release_eligible == run2.is_release_eligible
    assert len(run1.findings) == len(run2.findings)

    # Check evidence hashes match
    hashes1 = [f.evidence_ref.get("evidence_hash") for f in run1.findings]
    hashes2 = [f.evidence_ref.get("evidence_hash") for f in run2.findings]
    assert hashes1 == hashes2


def test_inspection_workflow_local_artifact_execution(temp_storage: LocalDatasetStorage):
    """
    Verify executing the inspection workflow on an immutable artifact stored locally in Environment B.
    Reads from storage, profiles, scans PII, evaluates quality, and calculates risk score.
    """
    workflow = DatasetInspectionWorkflow(storage=temp_storage)

    dataset_id = uuid.uuid4()
    csv_bytes = (
        "device_id,firmware_version,battery_pct\n"
        "D-101,v2.4.1,98\n"
        "D-102,v2.4.1,84\n"
        "D-103,v2.3.9,45\n"
    ).encode("utf-8")

    artifact_ref, file_size, content_hash = temp_storage.store_dataset(
        dataset_id=dataset_id,
        version_number=1,
        content=csv_bytes,
        ext="csv",
    )

    result = workflow.execute_inspection(
        dataset_id=dataset_id,
        version_number=1,
        artifact_ref=artifact_ref,
    )

    assert result.dataset_id == dataset_id
    assert result.status == InspectionStatus.COMPLETED
    assert result.summary_report["profiling"]["row_count"] == 3
    assert result.is_release_eligible is True


def test_inspection_persistence_and_cloud_endpoints(client: TestClient, temp_storage: LocalDatasetStorage):
    """
    Integration test: Ingest dataset, register metadata, execute complete inspection,
    and persist results into the Cloud Control Plane via POST /api/v1/inspections/record.
    Verify retrieval via GET /api/v1/inspections/{id} and /dataset/{id}.
    """
    # 1. Ingest dataset locally
    csv_content = (
        "customer_id,email,annual_spend\n"
        "C01,customer1@retail.com,1200.50\n"
        "C02,customer2@retail.com,450.00\n"
        "C03,customer3@retail.com,3200.10\n"
    ).encode("utf-8")

    worker = LocalIngestionWorker(storage=temp_storage)
    ingestion_payload = worker.process_local_file_or_stream(
        filename="retail_customers.csv",
        source=csv_content,
        dataset_name="Retail Customers",
    )

    # 2. Register metadata with Cloud Control Plane
    reg_res = client.post(
        "/api/v1/datasets/register-metadata",
        json={
            "dataset_id": str(ingestion_payload.dataset_id),
            "dataset_name": ingestion_payload.dataset_name,
            "description": ingestion_payload.description,
            "content_hash": ingestion_payload.content_hash,
            "file_format": ingestion_payload.file_format,
            "file_size": ingestion_payload.file_size,
            "local_artifact_ref": ingestion_payload.local_artifact_ref,
            "profile": ingestion_payload.profile,
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    reg_data = reg_res.json()
    version_id = reg_data["version_id"]

    # 3. Run complete inspection workflow locally
    workflow = DatasetInspectionWorkflow(storage=temp_storage)
    inspection_result = workflow.execute_inspection(
        dataset_id=ingestion_payload.dataset_id,
        dataset_version_id=uuid.UUID(version_id),
        version_number=1,
        artifact_ref=ingestion_payload.local_artifact_ref,
    )

    # 4. Post inspection run outbound to Cloud Control Plane
    inspection_payload = inspection_result.to_inspection_run_create().model_dump(mode="json")
    record_res = client.post("/api/v1/inspections/record", json=inspection_payload)
    assert record_res.status_code == 201, record_res.text
    record_data = record_res.json()

    inspection_id = record_data["id"]
    assert record_data["dataset_id"] == str(ingestion_payload.dataset_id)
    assert record_data["dataset_version_id"] == version_id
    assert record_data["status"] == "COMPLETED"
    assert record_data["findings_count"] >= 1

    # 5. Retrieve inspection run details
    get_res = client.get(f"/api/v1/inspections/{inspection_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["id"] == inspection_id
    assert len(get_data["findings"]) == record_data["findings_count"]

    # 6. List inspection runs for dataset
    list_res = client.get(f"/api/v1/inspections/dataset/{ingestion_payload.dataset_id}")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == inspection_id

    # 7. List findings for version
    findings_res = client.get(f"/api/v1/inspections/versions/{version_id}/findings")
    assert findings_res.status_code == 200
    findings_data = findings_res.json()
    assert len(findings_data) == record_data["findings_count"]


def test_zero_raw_data_leakage_guarantee():
    """
    Security Invariant Test:
    Ensures that raw dataset strings, confidential names, or private credentials
    NEVER appear in the inspection run summary report, findings, or evidence references.
    """
    workflow = DatasetInspectionWorkflow()

    canary_email = "super_canary_secret_value_987654@classified.org"
    canary_name = "ClassifiedCanaryIndividual"
    canary_phone = "800-555-9876"

    csv_content = (
        f"id,name,email,phone\n"
        f"1,{canary_name},{canary_email},{canary_phone}\n"
    ).encode("utf-8")

    result = workflow.execute_inspection(
        dataset_id=uuid.uuid4(),
        dataset_version_id=uuid.uuid4(),
        version_number=1,
        content=csv_content,
        file_format="csv",
    )

    # Serialize complete result to JSON
    serialized = json.dumps(result.to_dict())

    # Assert canaries do NOT exist anywhere in serialized output
    assert canary_email not in serialized
    assert canary_name not in serialized
    assert canary_phone not in serialized
    assert "super_canary_secret" not in serialized
    assert "classified.org" not in serialized
