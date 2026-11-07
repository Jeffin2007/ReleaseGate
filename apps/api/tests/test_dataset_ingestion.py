"""
Automated unit and integration tests for local dataset ingestion,
cryptographic hashing, deterministic Pandas profiling, secure local storage,
and Cloud Control Plane metadata-only registration contracts.
"""

import hashlib
import io
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from local_worker.ingestion_service import LocalIngestionWorker, SanitizedIngestionPayload
from local_worker.secure_storage import LocalDatasetStorage
from local_worker.validator import DatasetEmptyError, DatasetValidationError, validate_dataset_upload


def test_cloud_control_plane_rejects_raw_upload_routes(client: TestClient):
    """
    Verify that the Cloud Control Plane API does NOT expose any raw file upload routes
    (such as POST /api/v1/datasets/ingest or /api/v1/datasets/upload).
    """
    csv_bytes = b"col1,col2\n10,20\n"
    response = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code in (404, 405), (
        f"Cloud API must not accept raw file uploads; expected 404/405, got {response.status_code}"
    )


def test_local_worker_csv_ingestion_and_metadata_registration(client: TestClient, temp_storage: LocalDatasetStorage):
    """Verify local worker ingestion and metadata registration with the Cloud Control Plane."""
    csv_content = (
        "user_id,email,age,income,country\n"
        "1,alice@example.com,28,75000,US\n"
        "2,bob@example.com,,82000,CA\n"
        "3,charlie@example.com,35,,US\n"
        "4,david@example.com,42,105000,UK\n"
        "1,alice@example.com,28,75000,US\n"  # Duplicate row
    ).encode("utf-8")

    expected_hash = hashlib.sha256(csv_content).hexdigest().lower()

    # Process dataset locally inside the Local Data Processing Plane
    worker = LocalIngestionWorker(storage=temp_storage)
    payload: SanitizedIngestionPayload = worker.process_local_file_or_stream(
        filename="customer_churn.csv",
        source=csv_content,
        dataset_name="Customer Churn Study",
        description="Q3 Churn demographics",
    )

    assert payload.dataset_name == "Customer Churn Study"
    assert payload.version_number == 1
    assert payload.content_hash == expected_hash

    # Register sanitized metadata outbound to Cloud Control Plane
    reg_res = client.post(
        "/api/v1/datasets/register-metadata",
        json={
            "dataset_id": str(payload.dataset_id),
            "dataset_name": payload.dataset_name,
            "description": payload.description,
            "content_hash": payload.content_hash,
            "file_format": payload.file_format,
            "file_size": payload.file_size,
            "local_artifact_ref": payload.local_artifact_ref,
            "profile": payload.profile,
        },
    )
    assert reg_res.status_code == 201
    reg_payload = reg_res.json()

    assert reg_payload["dataset_name"] == "Customer Churn Study"
    assert reg_payload["content_hash"] == expected_hash
    assert reg_payload["local_artifact_ref"] == payload.local_artifact_ref

    profile = reg_payload["profile"]
    assert profile["row_count"] == 5
    assert profile["column_count"] == 5
    assert profile["duplicate_row_count"] == 1
    assert profile["null_counts"]["age"] == 1


def test_local_worker_xlsx_ingestion_and_profiling(client: TestClient, temp_storage: LocalDatasetStorage):
    """Verify local worker ingestion and profiling of an Excel (XLSX) workbook."""
    df = pd.DataFrame(
        {
            "product_id": [101, 102, 103, 104],
            "product_name": ["Widget A", "Widget B", "Widget C", "Widget D"],
            "unit_price": [19.99, None, 45.00, 12.50],
            "in_stock": [True, True, False, True],
        }
    )
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    xlsx_bytes = buffer.getvalue()
    expected_hash = hashlib.sha256(xlsx_bytes).hexdigest().lower()

    worker = LocalIngestionWorker(storage=temp_storage)
    payload = worker.process_local_file_or_stream(
        filename="products_catalog.xlsx",
        source=xlsx_bytes,
        dataset_name="Product Catalog",
    )

    assert payload.content_hash == expected_hash
    assert payload.file_format == "xlsx"

    reg_res = client.post(
        "/api/v1/datasets/register-metadata",
        json={
            "dataset_id": str(payload.dataset_id),
            "dataset_name": payload.dataset_name,
            "content_hash": payload.content_hash,
            "file_format": payload.file_format,
            "file_size": payload.file_size,
            "local_artifact_ref": payload.local_artifact_ref,
            "profile": payload.profile,
        },
    )
    assert reg_res.status_code == 201


def test_local_worker_json_ingestion_and_profiling(client: TestClient, temp_storage: LocalDatasetStorage):
    """Verify local worker ingestion and profiling of a JSON record dataset."""
    json_bytes = (
        '[\n'
        '  {"employee_id": "E-01", "department": "Security", "clearance": "Top Secret"},\n'
        '  {"employee_id": "E-02", "department": "Legal", "clearance": "Confidential"},\n'
        '  {"employee_id": "E-03", "department": null, "clearance": "Public"}\n'
        ']'
    ).encode("utf-8")
    expected_hash = hashlib.sha256(json_bytes).hexdigest().lower()

    worker = LocalIngestionWorker(storage=temp_storage)
    payload = worker.process_local_file_or_stream(
        filename="staff.json",
        source=json_bytes,
        dataset_name="Staff Clearances",
    )

    assert payload.content_hash == expected_hash
    assert payload.file_format == "json"

    reg_res = client.post(
        "/api/v1/datasets/register-metadata",
        json={
            "dataset_id": str(payload.dataset_id),
            "dataset_name": payload.dataset_name,
            "content_hash": payload.content_hash,
            "file_format": payload.file_format,
            "file_size": payload.file_size,
            "local_artifact_ref": payload.local_artifact_ref,
            "profile": payload.profile,
        },
    )
    assert reg_res.status_code == 201


def test_unsupported_file_extension_rejected(temp_storage: LocalDatasetStorage):
    """Verify unsupported extensions (e.g. .pdf, .exe, .py) are rejected locally."""
    worker = LocalIngestionWorker(storage=temp_storage)
    dummy_pdf = b"%PDF-1.4 header contents..."
    with pytest.raises(DatasetValidationError) as exc_info:
        worker.process_local_file_or_stream(filename="report.pdf", source=dummy_pdf)
    assert "Unsupported file format" in str(exc_info.value)


def test_executable_signature_rejected():
    """Verify files with malicious executable signatures are strictly rejected locally."""
    with pytest.raises(DatasetValidationError) as exc_info:
        validate_dataset_upload("data.csv", b"MZ\x90\x00\x03\x00\x00\x00")
    assert "Security violation" in str(exc_info.value)

    with pytest.raises(DatasetValidationError) as exc_info:
        validate_dataset_upload("data.csv", b"\x7fELF\x02\x01\x01\x00")
    assert "Security violation" in str(exc_info.value)


def test_empty_dataset_rejected(temp_storage: LocalDatasetStorage):
    """Verify zero-byte empty files are rejected locally."""
    worker = LocalIngestionWorker(storage=temp_storage)
    with pytest.raises(DatasetEmptyError) as exc_info:
        worker.process_local_file_or_stream(filename="empty.csv", source=b"")
    assert "Uploaded file is empty" in str(exc_info.value)


def test_dataset_versioning_and_immutability(client: TestClient, temp_storage: LocalDatasetStorage):
    """Verify dataset container supports multiple immutable versions."""
    worker = LocalIngestionWorker(storage=temp_storage)

    # Version 1
    v1_content = b"col1,col2\n10,20\n30,40"
    v1_hash = hashlib.sha256(v1_content).hexdigest().lower()
    p1 = worker.process_local_file_or_stream(
        filename="metrics.csv",
        source=v1_content,
        dataset_name="Performance Metrics",
    )

    res1 = client.post(
        "/api/v1/datasets/register-metadata",
        json={
            "dataset_id": str(p1.dataset_id),
            "dataset_name": p1.dataset_name,
            "content_hash": p1.content_hash,
            "file_format": p1.file_format,
            "file_size": p1.file_size,
            "local_artifact_ref": p1.local_artifact_ref,
            "profile": p1.profile,
        },
    )
    assert res1.status_code == 201
    dataset_id = p1.dataset_id

    # Version 2
    v2_content = b"col1,col2,col3\n10,20,30\n40,50,60\n70,80,90"
    v2_hash = hashlib.sha256(v2_content).hexdigest().lower()
    p2 = worker.process_local_file_or_stream(
        filename="metrics_v2.csv",
        source=v2_content,
        dataset_id=dataset_id,
        version_number=2,
    )

    res2 = client.post(
        "/api/v1/datasets/register-metadata",
        json={
            "dataset_id": str(p2.dataset_id),
            "dataset_name": p2.dataset_name,
            "content_hash": p2.content_hash,
            "file_format": p2.file_format,
            "file_size": p2.file_size,
            "local_artifact_ref": p2.local_artifact_ref,
            "profile": p2.profile,
        },
    )
    assert res2.status_code == 201

    # Query Cloud Control Plane for details
    get_res = client.get(f"/api/v1/datasets/{dataset_id}")
    assert get_res.status_code == 200
    dataset_details = get_res.json()
    assert len(dataset_details["versions"]) == 2

    # Verify Version 1 remains unchanged
    v1_record = dataset_details["versions"][0]
    assert v1_record["version_number"] == 1
    assert v1_record["content_hash"] == v1_hash
    assert v1_record["metadata"]["row_count"] == 2

    # Verify Version 2 record
    v2_record = dataset_details["versions"][1]
    assert v2_record["version_number"] == 2
    assert v2_record["content_hash"] == v2_hash
    assert v2_record["metadata"]["row_count"] == 3


def test_secure_storage_read_and_integrity_check(temp_storage: LocalDatasetStorage):
    """Verify secure storage writes file, prevents tampering, and resolves refs accurately."""
    import uuid

    dataset_id = uuid.uuid4()
    content = b"sensitive_user_id,ssn\nu1,123-45-6789\nu2,987-65-4321\n"
    expected_hash = hashlib.sha256(content).hexdigest().lower()

    artifact_ref, size, computed_hash = temp_storage.store_dataset(
        dataset_id=dataset_id,
        version_number=1,
        content=content,
        ext="csv",
    )
    assert computed_hash == expected_hash
    assert size == len(content)

    read_bytes = temp_storage.read_dataset(artifact_ref)
    assert read_bytes == content

    internal_path = temp_storage.resolve_ref_to_internal_path(artifact_ref)
    assert internal_path.is_file()
    assert expected_hash in internal_path.name
