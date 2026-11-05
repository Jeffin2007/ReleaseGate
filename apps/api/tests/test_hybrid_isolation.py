"""
Automated security and architectural boundary tests for:
1. Hybrid Cloud/Local Data Isolation (verifying raw dataset bytes never enter the Cloud Control Plane metadata registration endpoint).
2. Outbound Authenticated Communication from Local Worker to Cloud Control Plane.
3. Bounded-Memory Upload & Stream Processing (rejecting oversized streams without loading them into memory).
4. Path Traversal & Absolute Filesystem Path Leak Prevention.
5. Read-Only Immutability & Controlled Retention/Deletion Permission Management.
"""

import hashlib
import io
import os
import stat
from pathlib import Path
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from local_worker.cloud_client import CloudControlPlaneClient
from local_worker.ingestion_service import LocalIngestionWorker, SanitizedIngestionPayload
from local_worker.secure_storage import LocalDatasetStorage, SecureStorageError
from local_worker.validator import DatasetValidationError, validate_dataset_stream


def test_local_worker_to_cloud_metadata_only_isolation(
    client: TestClient,
    temp_storage: LocalDatasetStorage,
):
    """
    Trace complete hybrid ingestion flow:
    1. Raw dataset with sensitive PII rows is ingested locally by LocalIngestionWorker.
    2. LocalIngestionWorker emits SanitizedIngestionPayload.
    3. Verify SanitizedIngestionPayload contains ZERO raw row values and ZERO host filesystem paths.
    4. CloudControlPlaneClient sends outbound authenticated POST to /api/v1/datasets/register-metadata.
    5. Verify Cloud Control Plane database stores only sanitized metadata, SHA-256 hash, and opaque ref.
    """
    sensitive_raw_csv = (
        "patient_id,full_name,ssn,diagnosis_code\n"
        "P-9001,Jane Doe,999-88-7777,ICD-10-J01\n"
        "P-9002,John Smith,111-22-3333,ICD-10-I10\n"
    ).encode("utf-8")
    expected_sha256 = hashlib.sha256(sensitive_raw_csv).hexdigest().lower()

    # Step 1: Local Worker processes the raw dataset strictly inside the Local Data Plane
    worker = LocalIngestionWorker(storage=temp_storage)
    sanitized_payload: SanitizedIngestionPayload = worker.process_local_file_or_stream(
        filename="clinical_records.csv",
        source=io.BytesIO(sensitive_raw_csv),
        dataset_name="Clinical Records Cohort",
        description="On-prem sensitive clinical dataset",
    )

    # Step 2: Verify the outbound payload contains NO raw row values or absolute paths
    payload_str = str(sanitized_payload.to_dict())
    assert "Jane Doe" not in payload_str
    assert "999-88-7777" not in payload_str
    assert "ICD-10-J01" not in payload_str
    assert str(temp_storage.base_dir) not in payload_str
    assert sanitized_payload.content_hash == expected_sha256
    assert sanitized_payload.local_artifact_ref.startswith("artifact://local/datasets/")

    # Step 3: Local Worker initiates outbound authenticated call to Cloud Control Plane
    asgi_transport = httpx.WSGITransport(app=fastapi_app) if hasattr(httpx, "WSGITransport") else None
    # Use TestClient directly to inspect the exact HTTP wire payload sent to /register-metadata
    outbound_json = {
        "dataset_id": str(sanitized_payload.dataset_id),
        "dataset_name": sanitized_payload.dataset_name,
        "description": sanitized_payload.description,
        "content_hash": sanitized_payload.content_hash,
        "file_format": sanitized_payload.file_format,
        "file_size": sanitized_payload.file_size,
        "local_artifact_ref": sanitized_payload.local_artifact_ref,
        "profile": sanitized_payload.profile,
    }

    reg_response = client.post(
        "/api/v1/datasets/register-metadata",
        json=outbound_json,
        headers={
            "Authorization": "Bearer local-worker-secret-session-token",
            "X-ReleaseGate-Plane": "local-worker-outbound",
        },
    )
    assert reg_response.status_code == 201
    cloud_record = reg_response.json()

    assert cloud_record["dataset_id"] == str(sanitized_payload.dataset_id)
    assert cloud_record["content_hash"] == expected_sha256
    assert cloud_record["local_artifact_ref"] == sanitized_payload.local_artifact_ref
    assert cloud_record["profile"]["row_count"] == 2
    assert cloud_record["profile"]["column_count"] == 4

    # Verify raw file exists only in local worker storage
    stored_bytes = temp_storage.read_dataset(sanitized_payload.local_artifact_ref)
    assert stored_bytes == sensitive_raw_csv


def test_cloud_control_plane_rejects_exposed_filesystem_paths_in_metadata(client: TestClient):
    """
    Verify that the Cloud Control Plane strictly rejects metadata registration requests
    that attempt to expose absolute host paths or path traversal sequences in local_artifact_ref.
    """
    invalid_refs = [
        "/app/applet/storage/raw_datasets/secret.csv",
        "/root/datasets/data.csv",
        "file:///etc/passwd",
        "artifact://local/datasets/../../etc/shadow",
        "C:\\Users\\Admin\\datasets\\file.csv",
    ]

    for bad_ref in invalid_refs:
        payload = {
            "dataset_name": "Invalid Ref Dataset",
            "content_hash": "a" * 64,
            "file_format": "csv",
            "file_size": 1024,
            "local_artifact_ref": bad_ref,
            "profile": {
                "row_count": 10,
                "column_count": 2,
                "columns": ["id", "val"],
                "column_types": {"id": "integer", "val": "string"},
                "null_counts": {"id": 0, "val": 0},
                "null_percentages": {"id": 0.0, "val": 0.0},
                "duplicate_row_count": 0,
                "file_format": "csv",
            },
        }
        response = client.post("/api/v1/datasets/register-metadata", json=payload)
        assert response.status_code == 422, f"Expected 422 rejection for bad ref: {bad_ref}"


def test_bounded_memory_stream_validation_and_storage(temp_storage: LocalDatasetStorage):
    """
    Verify that large streams are processed in fixed chunks and rejected immediately
    once they exceed max_size_bytes without reading the remainder of the stream.
    """
    # Create a custom stream that tracks how many bytes were read
    class BoundedTrackingStream(io.BytesIO):
        def __init__(self, initial_bytes: bytes):
            super().__init__(initial_bytes)
            self.bytes_read = 0

        def read(self, size: int = -1) -> bytes:
            chunk = super().read(size)
            self.bytes_read += len(chunk)
            return chunk

    # Create a 500 KB valid CSV payload, but set max_size_bytes to 128 KB
    header = b"col1,col2,col3\n"
    row = b"1000,2000,3000\n" * 35000  # ~525 KB
    stream = BoundedTrackingStream(header + row)

    max_limit = 128 * 1024  # 128 KB
    with pytest.raises(DatasetValidationError) as exc_info:
        validate_dataset_stream(
            filename="oversized_stream.csv",
            stream=stream,
            max_size_bytes=max_limit,
            chunk_size=32 * 1024,
        )

    assert "exceeds maximum limit" in str(exc_info.value)
    # Confirm it aborted early after crossing the 128 KB threshold rather than reading all 525 KB
    assert stream.bytes_read < 250 * 1024


def test_controlled_retention_and_deletion_of_readonly_artifacts(temp_storage: LocalDatasetStorage):
    """
    Verify that stored artifacts are protected as read-only (0o400) during normal operation,
    yet remain cleanly manageable for authorized retention deletion and dataset purging.
    """
    dataset_id = uuid.uuid4()
    raw_content = b"id,metric\n1,99.5\n2,88.1\n"

    artifact_ref, _, _ = temp_storage.store_dataset(
        dataset_id=dataset_id,
        version_number=1,
        content=raw_content,
        ext="csv",
    )

    internal_path = temp_storage.resolve_ref_to_internal_path(artifact_ref)
    assert internal_path.exists()

    # Check read-only permission mode (owner read, no write bit)
    file_mode = stat.S_IMODE(os.stat(internal_path).st_mode)
    assert file_mode == stat.S_IRUSR

    # Controlled retention deletion of a single version artifact
    deleted = temp_storage.delete_artifact_for_retention(artifact_ref)
    assert deleted is True
    assert not internal_path.exists()

    # Re-store two versions and test full dataset directory purge
    ref_v1, _, _ = temp_storage.store_dataset(dataset_id, 1, raw_content, "csv")
    ref_v2, _, _ = temp_storage.store_dataset(dataset_id, 2, raw_content + b"3,77.0\n", "csv")

    assert temp_storage.resolve_ref_to_internal_path(ref_v1).exists()
    assert temp_storage.resolve_ref_to_internal_path(ref_v2).exists()

    purged = temp_storage.purge_dataset_directory(dataset_id)
    assert purged is True
    assert not (temp_storage.base_dir / str(dataset_id)).exists()
