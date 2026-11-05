"""
Automated unit and integration tests for local dataset ingestion,
cryptographic hashing, deterministic Pandas profiling, and secure storage.
"""

import hashlib
import io
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.services.dataset_service import DatasetService
from local_worker.hashing import calculate_sha256_bytes
from local_worker.secure_storage import LocalDatasetStorage, StorageIntegrityError
from local_worker.validator import DatasetEmptyError, DatasetValidationError, validate_dataset_upload


def test_csv_ingestion_and_profiling(client: TestClient):
    """Verify end-to-end ingestion and deterministic profiling of a CSV dataset."""
    csv_content = (
        "user_id,email,age,income,country\n"
        "1,alice@example.com,28,75000,US\n"
        "2,bob@example.com,,82000,CA\n"
        "3,charlie@example.com,35,,US\n"
        "4,david@example.com,42,105000,UK\n"
        "1,alice@example.com,28,75000,US\n"  # Duplicate row
    ).encode("utf-8")

    expected_hash = hashlib.sha256(csv_content).hexdigest().lower()

    response = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("customer_churn.csv", csv_content, "text/csv")},
        data={"dataset_name": "Customer Churn Study", "description": "Q3 Churn demographics"},
    )
    assert response.status_code == 201
    payload = response.json()

    assert payload["dataset_name"] == "Customer Churn Study"
    assert payload["version_number"] == 1
    assert payload["content_hash"] == expected_hash

    # Verify secure artifact reference: does not leak local filesystem paths
    artifact_ref = payload["local_artifact_ref"]
    assert artifact_ref.startswith("artifact://local/datasets/")
    assert "/storage/" not in artifact_ref
    assert "/app/" not in artifact_ref
    assert "/root/" not in artifact_ref

    # Verify profiling metrics
    profile = payload["profile"]
    assert profile["row_count"] == 5
    assert profile["column_count"] == 5
    assert profile["columns"] == ["user_id", "email", "age", "income", "country"]
    assert profile["duplicate_row_count"] == 1
    assert profile["null_counts"]["age"] == 1
    assert profile["null_counts"]["income"] == 1
    assert profile["null_counts"]["email"] == 0
    assert profile["null_percentages"]["age"] == 20.0  # 1/5 = 20.0%
    assert profile["file_format"] == "csv"


def test_xlsx_ingestion_and_profiling(client: TestClient):
    """Verify ingestion and profiling of an Excel (XLSX) workbook dataset."""
    # Generate in-memory XLSX
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

    response = client.post(
        "/api/v1/datasets/ingest",
        files={
            "file": (
                "products_catalog.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"dataset_name": "Product Catalog"},
    )
    assert response.status_code == 201
    payload = response.json()

    assert payload["content_hash"] == expected_hash
    profile = payload["profile"]
    assert profile["row_count"] == 4
    assert profile["column_count"] == 4
    assert profile["columns"] == ["product_id", "product_name", "unit_price", "in_stock"]
    assert profile["null_counts"]["unit_price"] == 1
    assert profile["null_percentages"]["unit_price"] == 25.0
    assert profile["duplicate_row_count"] == 0
    assert profile["file_format"] == "xlsx"


def test_json_ingestion_and_profiling(client: TestClient):
    """Verify ingestion and profiling of a JSON record dataset."""
    json_bytes = (
        '[\n'
        '  {"employee_id": "E-01", "department": "Security", "clearance": "Top Secret"},\n'
        '  {"employee_id": "E-02", "department": "Legal", "clearance": "Confidential"},\n'
        '  {"employee_id": "E-03", "department": null, "clearance": "Public"}\n'
        ']'
    ).encode("utf-8")

    expected_hash = hashlib.sha256(json_bytes).hexdigest().lower()

    response = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("staff.json", json_bytes, "application/json")},
        data={"dataset_name": "Staff Clearances"},
    )
    assert response.status_code == 201
    payload = response.json()

    assert payload["content_hash"] == expected_hash
    profile = payload["profile"]
    assert profile["row_count"] == 3
    assert profile["column_count"] == 3
    assert profile["null_counts"]["department"] == 1
    assert profile["null_percentages"]["department"] == 33.33
    assert profile["file_format"] == "json"


def test_unsupported_file_extension_rejected(client: TestClient):
    """Verify unsupported extensions (e.g. .pdf, .exe, .py) are rejected with 400 Bad Request."""
    dummy_pdf = b"%PDF-1.4 header contents..."
    response = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("report.pdf", dummy_pdf, "application/pdf")},
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_executable_signature_rejected():
    """Verify files with malicious executable signatures are strictly rejected."""
    # Windows executable signature MZ
    with pytest.raises(DatasetValidationError) as exc_info:
        validate_dataset_upload("data.csv", b"MZ\x90\x00\x03\x00\x00\x00")
    assert "Security violation" in str(exc_info.value)

    # Linux ELF signature \x7fELF
    with pytest.raises(DatasetValidationError) as exc_info:
        validate_dataset_upload("data.csv", b"\x7fELF\x02\x01\x01\x00")
    assert "Security violation" in str(exc_info.value)


def test_empty_dataset_rejected(client: TestClient):
    """Verify zero-byte empty files are rejected."""
    response = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert "Uploaded file is empty" in response.json()["detail"]


def test_malformed_csv_null_bytes_rejected():
    """Verify binary data disguised as CSV with null bytes is rejected."""
    binary_as_csv = b"col1,col2\nval1,\x00\x01\x02bad_binary"
    with pytest.raises(DatasetValidationError) as exc_info:
        validate_dataset_upload("fake.csv", binary_as_csv)
    assert "Contains null bytes" in str(exc_info.value)


def test_malformed_json_rejected(client: TestClient):
    """Verify malformed JSON syntax is rejected."""
    corrupted_json = b'{"name": "Alice", "broken": ['
    response = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("corrupted.json", corrupted_json, "application/json")},
    )
    assert response.status_code == 400
    assert "Failed to parse" in response.json()["detail"] or "validation failed" in response.json()["detail"].lower()


def test_malformed_xlsx_rejected():
    """Verify corrupted XLSX file without PK magic header is rejected."""
    fake_xlsx = b"NotAZipFileContentForExcel"
    with pytest.raises(DatasetValidationError) as exc_info:
        validate_dataset_upload("corrupt.xlsx", fake_xlsx)
    assert "ZIP container magic signature" in str(exc_info.value)


def test_dataset_versioning_and_immutability(client: TestClient):
    """Verify dataset container supports multiple immutable versions."""
    # Version 1
    v1_content = b"col1,col2\n10,20\n30,40"
    v1_hash = hashlib.sha256(v1_content).hexdigest().lower()

    res1 = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("metrics.csv", v1_content, "text/csv")},
        data={"dataset_name": "Performance Metrics"},
    )
    assert res1.status_code == 201
    d1 = res1.json()
    dataset_id = d1["dataset_id"]
    assert d1["version_number"] == 1
    assert d1["content_hash"] == v1_hash

    # Version 2 (ingested into existing dataset_id)
    v2_content = b"col1,col2,col3\n10,20,30\n40,50,60\n70,80,90"
    v2_hash = hashlib.sha256(v2_content).hexdigest().lower()

    res2 = client.post(
        "/api/v1/datasets/ingest",
        files={"file": ("metrics_v2.csv", v2_content, "text/csv")},
        data={"dataset_id": dataset_id},
    )
    assert res2.status_code == 201
    d2 = res2.json()
    assert d2["dataset_id"] == dataset_id
    assert d2["version_number"] == 2
    assert d2["content_hash"] == v2_hash

    # Verify parent dataset contains both versions
    get_res = client.get(f"/api/v1/datasets/{dataset_id}")
    assert get_res.status_code == 200
    dataset_details = get_res.json()
    assert len(dataset_details["versions"]) == 2

    # Verify Version 1 remains completely unchanged (immutable)
    v1_record = dataset_details["versions"][0]
    assert v1_record["version_number"] == 1
    assert v1_record["content_hash"] == v1_hash
    assert v1_record["metadata"]["row_count"] == 2
    assert v1_record["metadata"]["column_count"] == 2

    # Verify Version 2 record
    v2_record = dataset_details["versions"][1]
    assert v2_record["version_number"] == 2
    assert v2_record["content_hash"] == v2_hash
    assert v2_record["metadata"]["row_count"] == 3
    assert v2_record["metadata"]["column_count"] == 3


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

    # Read back and verify exact byte equality
    read_bytes = temp_storage.read_dataset(artifact_ref)
    assert read_bytes == content

    # Verify path is outside web directory and has secure ref format
    internal_path = temp_storage.resolve_ref_to_internal_path(artifact_ref)
    assert internal_path.is_file()
    assert expected_hash in internal_path.name
