# ReleaseGate Ingestion Boundary Audit & Local Ingestion Enforcement

> **Document ID**: Prompt 04B  
> **Reference Baseline**: Frozen ReleaseGate Architecture v1.0  
> **Topic**: Hybrid Data Plane / Control Plane Boundary Enforcement  

---

## 1. Executive Summary & Audit Findings

An architectural audit of the dataset ingestion pipeline was performed to verify whether raw dataset bytes traverse or temporarily enter the Cloud Control Plane process memory.

### Identified Violation in Initial Design
In the initial implementation, `POST /api/v1/datasets/ingest` was exposed directly on the Cloud Control Plane FastAPI router (`apps/api/app/api/v1/endpoints/datasets.py`). While the endpoint utilized streaming via `file.file` (`SpooledTemporaryFile`) to process data, the raw file bytes were still transmitted over the network and entered the Cloud Control Plane process memory space.

Per the ReleaseGate Architecture Baseline v1.0:
> *Streaming, `SpooledTemporaryFile`, or forwarding through the cloud API does NOT constitute isolation. If raw bytes enter the cloud process, the hybrid boundary is violated.*

---

## 2. Chosen Design & Architectural Correction

To enforce true data isolation without introducing unprotected localhost services or exposed inbound worker ports, ReleaseGate implements the following corrected design:

### 1. Total Removal of Raw Upload Routes from Cloud Control Plane
`POST /api/v1/datasets/ingest` has been **completely removed** from `apps/api/app/api/v1/endpoints/datasets.py`. The Cloud Control Plane API exposes **zero** endpoints accepting `UploadFile` or multipart file uploads. Attempting to POST raw files to the Cloud Control Plane returns `HTTP 404 Not Found`.

### 2. Pure Metadata Registration Endpoint (`POST /api/v1/datasets/register-metadata`)
The Cloud Control Plane accepts **only** sanitized metadata via `POST /api/v1/datasets/register-metadata`. The request model (`DatasetMetadataRegistrationRequest`) enforces:
* **Zero Raw Bytes**: Payload contains only dataset name, description, SHA-256 `content_hash`, `file_format`, `file_size`, opaque `local_artifact_ref`, and deterministic `profile` statistics.
* **Opaque Artifact References**: `local_artifact_ref` must use the `artifact://local/datasets/...` URI scheme. Any payload containing absolute host paths (e.g. `/app/`, `/root/`, `/storage/`, `..`, `\`) is rejected with `HTTP 422`.

### 3. On-Prem Local Processing Engine (`LocalIngestionWorker`)
Raw dataset validation, chunked SHA-256 content hashing, deterministic Pandas profiling, and read-only file storage execute **exclusively inside the Local Data Processing Plane** (`local-worker/ingestion_service.py`).

### 4. Outbound Authenticated Cloud Communication (`CloudControlPlaneClient`)
The Local Ingestion Worker is not publicly exposed to the internet. Upon completing local validation, profiling, and storage, `CloudControlPlaneClient` (`local-worker/cloud_client.py`) makes an **outbound authenticated HTTP request** (`Authorization: Bearer <token>`, `X-ReleaseGate-Plane: local-worker-outbound`) to register the sanitized metadata payload with the Cloud Control Plane.

---

## 3. Concrete Process & Network Boundary Diagram

```
+-----------------------------------------------------------------------------------------+
|                        LOCAL DATA PROCESSING PLANE (On-Prem / Edge)                     |
|                                                                                         |
|  [Local File / Source Stream]                                                           |
|               |                                                                         |
|               v                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | LocalIngestionWorker (local-worker/ingestion_service.py)                         |  |
|  |                                                                                   |  |
|  |  1. validate_dataset_stream(): Header magic bytes & format validation (.csv, .json, .xlsx) |
|  |  2. store_dataset_stream(): Fixed 64 KB chunk streaming to local read-only storage |  |
|  |     (storage/raw_datasets/...) & on-the-fly SHA-256 digest calculation.           |  |
|  |  3. DatasetProfiler.profile(): Deterministic Pandas profiling in local memory.   |  |
|  |  4. Produces SanitizedIngestionPayload (Metadata, Hash, Profile, Opaque Ref).     |  |
|  +-----------------------------------------|-----------------------------------------+  |
+--------------------------------------------|--------------------------------------------+
                                             | Outbound Authenticated HTTP POST
                                             | Header: Authorization: Bearer <worker_token>
                                             | Body: DatasetMetadataRegistrationRequest
                                             | (Metadata, SHA-256 Hash, Profile)
                                             | NO RAW DATASET BYTES / NO HOST PATHS
+--------------------------------------------v--------------------------------------------+
|                       CLOUD CONTROL PLANE API (apps/api/app/main.py)                    |
|                                                                                         |
|  POST /api/v1/datasets/register-metadata                                                |
|  1. Validates schema & rejects any exposed host paths (/app/, /root/, /storage/).      |
|  2. DatasetService.register_dataset_metadata() records Dataset & DatasetVersion in DB. |
|  3. Returns DatasetIngestResponse to Local Worker.                                      |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | PostgreSQL Database (13 Core Entities)                                           |  |
|  | Stores Dataset container & immutable DatasetVersion records.                      |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

---

## 4. Memory Bounds, Cleanup, Permissions & Privacy Controls

1. **Bounded Memory Usage**: Upload validation (`validate_dataset_stream`) and storage (`store_dataset_stream`) stream data in fixed 64 KB chunks, evaluating maximum size limits (100 MB default) on the fly without buffering entire files in RAM.
2. **File Permissions**: Raw datasets stored locally are locked with read-only permissions (`0o400` / owner read-only) immediately after writing.
3. **Controlled Retention Deletion**: `LocalDatasetStorage.delete_artifact_for_retention()` and `purge_dataset_directory()` temporarily restore owner write bits (`0o600` / `0o700`) prior to unlinking, enabling clean retention management without permission errors.
4. **Log & Response Hygiene**: Centralized logging filter (`SensitiveRedactionFilter`) scrubs Bearer tokens, DB credentials, API keys, SSNs, and credit cards.

---

## 5. Verification Evidence & Confirmation

The backend test suite was run with 33 comprehensive unit, integration, and security tests in `apps/api/tests/`:

* `test_cloud_control_plane_rejects_raw_upload_routes`: Proves `POST /api/v1/datasets/ingest` returns `404/405` on the Cloud Control Plane.
* `test_local_worker_to_cloud_metadata_only_isolation`: Traces complete local ingestion and verifies that outbound JSON payloads contain zero raw sensitive dataset values.
* `test_cloud_control_plane_rejects_exposed_filesystem_paths_in_metadata`: Confirms rejection of exposed host path strings (`/app/`, `/root/`, `/storage/`, `..`) in `local_artifact_ref`.
* `test_bounded_memory_stream_validation_and_storage`: Confirms streams exceeding size bounds abort early without buffering the remaining payload in memory.
* `test_controlled_retention_and_deletion_of_readonly_artifacts`: Confirms read-only files are cleanly removable during authorized retention cycles.

### Explicit Confirmation Statement
> **CONFIRMED**: Raw dataset bytes **NEVER** enter, traverse, or get temporarily processed by the Cloud Control Plane FastAPI process. All raw file processing executes exclusively on the Local Data Processing Plane.
