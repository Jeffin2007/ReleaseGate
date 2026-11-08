# ReleaseGate — Authoritative Architecture Specification (Baseline v1.0)

> **Document Status**: Frozen Reference Baseline v1.0  
> **Target System**: ReleaseGate Evidence-Driven AI Data Release Governance Agent  

---

## 1. System Vision & Architecture Principles

ReleaseGate is an **evidence-driven, autonomous AI data release governance system** designed to evaluate, sanitize, verify, and authorize sensitive dataset releases across enterprise environments. ReleaseGate is engineered as a hybrid AI governance agent operating with bounded autonomy, explicit execution constraints, independent review cycles, and cryptographic human authorization.

### Core Operating Principles
1. **AI Recommends, Humans Authorize**: AI agents analyze data, detect vulnerabilities, and propose transformations, but **never** independently authorize a dataset publication.
2. **Version-Bound Authorization**: Approvals are bound to an exact SHA-256 binary hash (`proposed_output_hash`), not merely a dataset name or release request ID.
3. **Local Data Plane Isolation**: Raw sensitive datasets remain strictly on the local data processing plane. Only sanitized metadata, aggregate risk indicators, Presidio entity counts, and content hashes are transmitted to the cloud control plane.
4. **Two-Model Review Architecture**: An independent AI reviewer ("Challenger") must audit and challenge the primary agent's ("Investigator") remediation proposal.
5. **Bounded Agent Loop**: The local remediation agent operates within hard execution boundaries (max 12 tool calls, 8 reasoning steps, 1 controlled rewrite, 3 execution retry attempts).
6. **Auditable & Idempotent Execution**: All tool invocations and state transitions produce immutable, append-only audit events. Repeated operations with identical idempotency keys execute idempotently.
7. **Global Emergency Halt (Circuit Breaker)**: System administrators can instantly trigger a global pause switch to halt all pending and executing releases across the organization.
8. **Fail-Closed Security**: Missing proof, checksum mismatches, tool failures, or unhandled policy violations cause immediate job rejection.

---

## 2. Hybrid Architecture: Control Plane & Data Plane

ReleaseGate separates concerns into two distinct execution environments:

```
+-----------------------------------------------------------------------------------+
|                           A. CLOUD CONTROL PLANE (Cloud)                          |
|                                                                                   |
|   +-----------------------+    +-----------------------+    +------------------+  |
|   |   React Dashboard     |    |   FastAPI Control API |    | Authentication   |  |
|   |   (User Interface)    | <->|   & Auth / RBAC       | <->| & RBAC Policies  |  |
|   +-----------------------+    +-----------+-----------+    +------------------+  |
|                                            |                                      |
|   +-----------------------+                v                +------------------+  |
|   |   Approval Queue      | <---> +------------------+ <--->| Independent AI   |  |
|   |   (Human-in-the-Loop) |       | Job Coordination |      | Reviewer Model   |  |
|   +-----------------------+       | Service          |      | (Challenger)     |  |
|                                   +--------+---------+      +------------------+  |
|   +-----------------------+                |                                      |
|   | PostgreSQL DB         | <--------------+ (Reads/Writes Audit Ledger & State)  |
|   | (13 Core Entities)    |                                                       |
|   +-----------------------+                                                       |
+--------------------------------------------|--------------------------------------+
                                             | Outbound Authenticated Job Channel
                                             | (Signed Jobs / Sanitized Findings)
+--------------------------------------------v--------------------------------------+
|                          B. LOCAL DATA PLANE (On-Prem / Edge)                     |
|                                                                                   |
|   +-----------------------+       +-------------------+     +------------------+  |
|   | Local Agent Worker    | ----> | Local MCP Server  | --> | Inspection &     |  |
|   | (Bounded Orchestrator)|       | (12 Typed Tools)  |     | Profiler Engine  |  |
|   +-----------------------+       +---------+---------+     +--------+---------+  |
|               |                             |                        |            |
|               v                             v                        v            |
|   +-----------------------+       +-------------------+     +------------------+  |
|   | Encrypted Local File  |       | Presidio PII      |     | Transformation   |  |
|   | Storage (Raw Data)    |       | Detection Engine  |     | & Publication    |  |
|   +-----------------------+       +-------------------+     +------------------+  |
+-----------------------------------------------------------------------------------+
```

### Plane Responsibilities
* **Cloud Control Plane**: Hosts the React dashboard, FastAPI control API (`/api/v1/datasets/register-metadata`), PostgreSQL relational state machine, RBAC engine, human approval queue, independent reviewer model integration, and append-only audit event service. Receives **only** sanitized metadata, SHA-256 content hashes, opaque artifact references (`artifact://local/datasets/...`), and profiling summaries.
* **Local Data Processing Plane**: Runs the local agent worker (`LocalIngestionWorker`), MCP tool server, Pandas dataset profiler, Microsoft Presidio PII detection engine, data quality validator, transformation engine, local encrypted/read-only file storage (`LocalDatasetStorage`), and publication adapter. Owns all raw dataset bytes, bounded-memory stream validation, SHA-256 hashing, and deterministic profiling.
* **Network Isolation**: The local worker is never publicly exposed and initiates outbound authenticated HTTPS calls (`CloudControlPlaneClient`) to the cloud control plane. The local MCP server is never exposed to the public internet.

---

## 3. Complete 9-Step Governance Workflow

```
[1. User Upload Request via React Dashboard]
       |
       v
[2. FastAPI Auth/RBAC Verification & Job Coordination]
       |
       v
[3. Signed Job Request Sent to Local Agent Worker]
       |
       v
[4. Local Worker Initiates Bounded Agent Loop (Primary Model + Local MCP Server)]
       |
       v
[5. MCP Server Executes Tools (inspect_dataset, detect_sensitive_data, validate_data_quality, etc.)]
       |
       v
[6. Independent Reviewer Evaluates Findings -> Submits Decision to API & Approval Queue]
       |
       v
[7. Human Steward Review & Hash-Bound Approval Token Issuance]
       |
       v
[8. Signed Approved Command Sent to Local Worker -> Executes Publication Adapter]
       |
       v
[9. Publication Verification Recorded in PostgreSQL Audit Event Ledger]
```

---

## 4. Agent Architecture & Execution Limits

### Bounded Agent Loop Configuration
* **Maximum Tool Calls**: 12 tool invocations per investigation run.
* **Maximum Reasoning Iterations**: 8 steps.
* **Controlled Rewrite Limit**: Exactly 1 remediation rewrite allowed after a reviewer rejection.
* **Execution Retry Boundary**: Up to 3 execution attempts with exponential backoff.
* **Explicit Stop Reasons**: `COMPLETED`, `HUMAN_APPROVAL_REQUIRED`, `REVIEW_REJECTED`, `MAX_ITERATIONS_REACHED`, `TOOL_VALIDATION_FAILED`, `MODEL_TIMEOUT`, `POLICY_BLOCKED`, `EXECUTION_FAILED`, `SYSTEM_PAUSED`.

### Agent Role Breakdown

| Role | Responsibility |
| :--- | :--- |
| **Planner** | Determines inspection sequence based on dataset policy rules. |
| **Primary Agent (Investigator)** | Analyzes inspection evidence and generates risk proposals. |
| **Tool Validator** | Validates tool names and parameters against MCP JSON schemas. |
| **Tool Executor** | Invokes local MCP tools securely. |
| **Independent Reviewer (Challenger)** | Audits primary findings using an isolated model context. |
| **Approval Manager** | Collects human sign-offs and verifies cryptographic hashes. |
| **Execution Manager** | Triggers publication tools upon valid authorization. |
| **Audit Manager** | Records all agent actions to the PostgreSQL audit log. |

---

## 5. Model Context Protocol (MCP) Tool Registry (All 12 Tools)

The local MCP server exposes exactly 12 schema-validated tools:

| # | Tool Name | Description |
| :-: | :--- | :--- |
| 1 | `inspect_dataset` | Profile dataset structure, row counts, data types, and null distribution. |
| 2 | `detect_sensitive_data` | Execute Microsoft Presidio PII scanning across tabular/text columns. |
| 3 | `validate_data_quality` | Run data quality checks, constraint rules, and anomaly detection. |
| 4 | `check_release_policy` | Evaluate dataset metadata and profile against organizational release policies. |
| 5 | `generate_risk_report` | Compute aggregate risk score (0-100) and generate risk breakdown report. |
| 6 | `propose_transformation` | Formulate sanitization plan (masking, redaction, hashing, generalization). |
| 7 | `prepare_release` | Stage sanitized dataset version and calculate its SHA-256 output hash. |
| 8 | `submit_for_review` | Package findings and evidence JSONs for the independent AI reviewer. |
| 9 | `get_approval_status` | Query the human approval queue status and hash verification state. |
| 10 | `publish_dataset` | Execute final publication through authorized destination adapters. |
| 11 | `verify_publication` | Verify target destination receipt, accessibility, and hash matching. |
| 12 | `withdraw_release` | Cancel or recall a release request in progress or on hold. |

### 5.1 Complete Dataset Inspection Workflow (Prompt 10)

The `DatasetInspectionWorkflow` pipeline (`local_worker.inspection_pipeline`) coordinates four deterministic inspection engines into an auditable, end-to-end governance process executing exclusively inside Environment B (Local Processing Plane):

```
+-----------------------------------------------------------------------------------------------+
|                             Local Processing Plane (Environment B)                            |
|                                                                                               |
|  [Raw Dataset / Artifact]                                                                     |
|            |                                                                                  |
|            v                                                                                  |
|  +--------------------+      +--------------------+      +--------------------+               |
|  |  Dataset Profiler  | ---> |   PII Detector     | ---> | Quality Validator  |               |
|  |  (Pandas Engine)   |      | (Presidio Analyzer)|      |  (Rule Engine)     |               |
|  +--------------------+      +--------------------+      +--------------------+               |
|            |                           |                           |                          |
|            | [Metrics]                 | [PII Findings]            | [Quality Issues]         |
|            +---------------------------+---------------------------+                          |
|                                        |                                                      |
|                                        v                                                      |
|                             +--------------------+                                            |
|                             |   Policy Engine    |                                            |
|                             |  (100-Point Model) |                                            |
|                             +--------------------+                                            |
|                                        |                                                      |
|                                        v                                                      |
|                       +---------------------------------+                                     |
|                       |  Auditable Inspection Result    |                                     |
|                       |  - Risk Score & Band (0-100)    |                                     |
|                       |  - Release Eligibility Decision |                                     |
|                       |  - Granular Findings (Zero Raw) |                                     |
|                       |  - Unified Summary Report       |                                     |
|                       +---------------------------------+                                     |
|                                        |                                                      |
+----------------------------------------|------------------------------------------------------+
                                         | Outbound HTTP POST /api/v1/inspections/record
                                         v (Sanitized Metadata, Hashes, Coordinates Only)
+-----------------------------------------------------------------------------------------------+
|                            Cloud Control Plane (Environment A)                                |
|                                                                                               |
|  FastAPI Endpoints:                                                                           |
|  - POST /api/v1/inspections/record              -> Persists InspectionRun & Findings          |
|  - GET  /api/v1/inspections/{id}                -> Retrieves run with granular findings       |
|  - GET  /api/v1/inspections/dataset/{id}        -> Lists runs for dataset container           |
|  - GET  /api/v1/inspections/versions/{id}/findings -> Lists findings for version (filters)   |
|                                                                                               |
|  PostgreSQL Database:                                                                         |
|  - `inspection_runs`: Status, risk_score, risk_band, policy_version, is_release_eligible      |
|  - `findings`: Categorized PII & Quality issues with cryptographic evidence hashes            |
+-----------------------------------------------------------------------------------------------+
```

#### Pipeline Guarantees:
1. **Zero Raw Value Leakage**: All findings and summary reports contain entity types, coordinates, counts, scores, and cryptographic hashes (`evidence_hash`). No raw text, confidential names, or private credentials ever enter outbound payloads.
2. **Deterministic Reproducibility**: Repeated inspections on identical dataset bytes yield byte-for-byte identical risk scores, risk bands, finding counts, and evidence references.
3. **Hard Blocking Overrides**: Critical policy violations (prohibited domain, forbidden licenses, critical credential leakage) immediately set `is_release_eligible=False` regardless of overall aggregate score.
4. **Tenant-Scoped Persistence**: Every inspection run and finding is strictly bound to an `organization_id`, ensuring fail-closed isolation across multi-tenant workspaces.

---

## 6. PostgreSQL Database Architecture (All 13 Entities)

The Cloud Control Plane relies on 13 relational database entities:

```
organizations (1) ---> (N) memberships <--- (N) users
      |
      +---> (N) datasets ---> (N) dataset_versions ---> (N) inspection_runs ---> (N) findings
                                    |
                                    +---> requested by release_requests
                                                 |
                                                 +---> reviewed by review_results
                                                 +---> requires approval_requests
                                                 +---> executes execution_records
```

### Implemented Persistence Entities (Prompt 09)

The Cloud Control Plane implements the core identity, workspace isolation, dataset catalog, and persistent inspection foundations using SQLAlchemy 2.0 with PostgreSQL-compatible native `Uuid` types and Alembic migration `001_initial_schema`:

1. **`organizations`**
   - Multi-tenant tenant workspace boundary.
   - Schema: `id` (UUID PK), `name` (String(255), unique, indexed), `slug` (String(100), unique, indexed), `is_active` (Boolean), `created_at` (DateTime), `updated_at` (DateTime).
   - Guarantees: All datasets, versions, inspection runs, and findings are strictly bound to an organization.

2. **`users`**
   - User identity and cryptographic credentials.
   - Schema: `id` (UUID PK), `email` (String(255), unique, indexed), `hashed_password` (String(255), PBKDF2-HMAC-SHA256 with 16-byte random salt), `full_name` (String(255), nullable), `is_active` (Boolean), `is_superuser` (Boolean), `created_at` (DateTime), `updated_at` (DateTime).

3. **`memberships`**
   - Multi-tenant RBAC mapping binding users to organizations with role designations.
   - Schema: `id` (UUID PK), `organization_id` (UUID FK $\rightarrow$ `organizations.id` ON DELETE CASCADE), `user_id` (UUID FK $\rightarrow$ `users.id` ON DELETE CASCADE), `role` (String(32), Enum: `ADMIN`, `STEWARD`, `AUDITOR`, `USER`), `is_active` (Boolean), `created_at` (DateTime).
   - Constraints: Unique constraint `uq_organization_user_membership` on `(organization_id, user_id)`.

4. **`datasets`**
   - Dataset metadata container.
   - Schema: `id` (UUID PK), `organization_id` (UUID FK $\rightarrow$ `organizations.id` ON DELETE CASCADE, indexed), `name` (String(255), indexed), `description` (Text), `current_version_id` (UUID, nullable), `created_by` (UUID, nullable), `created_at` (DateTime).

5. **`dataset_versions`**
   - Immutable version ledger containing cryptographic proofs and opaque local artifact references.
   - Schema: `id` (UUID PK), `dataset_id` (UUID FK $\rightarrow$ `datasets.id` ON DELETE CASCADE, indexed), `version_number` (Integer, indexed), `content_hash` (String(64), SHA-256), `file_format` (String(16)), `file_size` (BigInteger), `local_artifact_ref` (`artifact://local/datasets/...`), `dataset_metadata` (JSON profiling summary), `created_at` (DateTime).
   - Constraints: Unique constraint `uq_dataset_version` on `(dataset_id, version_number)`. Zero raw dataset bytes are stored.

6. **`inspection_runs`**
   - Execution log for local profiling, Presidio PII scanning, quality validation, and release policy evaluations.
   - Schema: `id` (UUID PK), `organization_id` (UUID FK $\rightarrow$ `organizations.id` ON DELETE CASCADE, indexed), `dataset_id` (UUID FK $\rightarrow$ `datasets.id` ON DELETE CASCADE, indexed), `dataset_version_id` (UUID FK $\rightarrow$ `dataset_versions.id` ON DELETE CASCADE, indexed), `inspection_type` (Enum: `FULL_SCAN`, `PII_DETECTION`, `QUALITY_VALIDATION`, `POLICY_EVALUATION`), `status` (Enum: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`), `risk_score` (Float, 0.0-100.0), `risk_band` (String(32)), `policy_version` (String(32)), `is_release_eligible` (Boolean), `summary_report` (JSON), `started_at` (DateTime), `completed_at` (DateTime).

7. **`findings`**
   - Granular privacy, quality, and policy violations associated with specific inspection runs and dataset versions.
   - Schema: `id` (UUID PK), `organization_id` (UUID FK $\rightarrow$ `organizations.id` ON DELETE CASCADE, indexed), `inspection_run_id` (UUID FK $\rightarrow$ `inspection_runs.id` ON DELETE CASCADE, indexed), `dataset_version_id` (UUID FK $\rightarrow$ `dataset_versions.id` ON DELETE CASCADE, indexed), `finding_type` (Enum: `PII`, `QUALITY`, `POLICY`, `PROVENANCE`), `category` (String(64)), `column_name` (String(255), nullable), `severity` (Enum: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL`), `occurrence_count` (Integer), `confidence_score` (Float, 0.0-1.0), `message` (Text), `evidence_ref` (JSON coordinates and counts, zero raw values), `created_at` (DateTime).

### Remaining Entities (Planned Phases 5–6)
8. `release_requests`: Release proposals linking dataset versions to target destinations.
9. `review_results`: Structured evaluation output from the independent AI reviewer.
10. `approval_requests`: Human authorization queue items bound to `artifact_hash`.
11. `execution_records`: Publication receipts, attempt counters, and idempotency keys.
12. `audit_events`: Append-only activity log with `previous_event_hash` and `event_hash`.
13. `scheduled_jobs`: APScheduler job registry for policy monitoring and approval expiration.

### Role-Based Access Control (RBAC) Matrix

| Role | Read Datasets / Reports | Ingest & Profile Datasets | Execute Inspections & Policies | Propose Releases & Mitigations | Override Policies & Manage Org |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`ADMIN`** | Yes | Yes | Yes | Yes | Yes |
| **`STEWARD`** | Yes | Yes | Yes | Yes | No |
| **`AUDITOR`** | Yes | No | No (Read-Only) | No | No |
| **`USER`** | Yes | Yes | Yes (Local) | No | No |

### Multi-Tenant Isolation & Relational Integrity Guarantees
- **Strict Tenant Partitioning**: Every dataset, inspection run, and finding has a mandatory or enforced `organization_id`. Database queries through `DatasetService`, `InspectionService`, and `IdentityService` enforce boundary filters.
- **Fail-Closed Access**: Queries attempting cross-tenant access raise `CrossOrganizationAccessError`, `OrganizationAccessDeniedError`, or `InspectionRunNotFoundError`.
- **Cascading Integrity**: Deletion of an organization cleanly cascades to all its memberships, datasets, versions, inspection runs, and findings via PostgreSQL `ON DELETE CASCADE` constraints, preserving global user accounts.
- **Immutability Protection**: `dataset_versions` enforces `uq_dataset_version (dataset_id, version_number)` to prevent mutation or replacement of previously published versions.

---

## 7. Risk Assessment Model

Risk scores are generated using a deterministic weighted formula:

$$\text{Risk Score} = \text{Sensitive Info}(35) + \text{Data Quality}(20) + \text{Licensing}(20) + \text{Metadata}(10) + \text{Policy Violations}(15)$$

* **0 – 19 (Low)**: Eligible for standard human approval queue.
* **20 – 39 (Moderate)**: Requires documented remediation proof.
* **40 – 69 (High)**: Mandatory dual-reviewer audit.
* **70 – 100 (Critical)**: **Immediate automated block** regardless of overall score.

---

## 8. Governance & Security Controls

* **Hash-Bound Authorization**: Approval tokens explicitly bind to the SHA-256 `proposed_output_hash`. Any post-approval modification invalidates authorization.
* **Idempotent Operations**: All execution requests require unique `idempotency_key` tokens to prevent duplicate runs.
* **Append-Only Audit Trail**: Audit events form a cryptographic hash chain (`previous_event_hash` $\rightarrow$ `event_hash`). Records cannot be edited or deleted by application users.
* **Emergency Global Pause Switch (Circuit Breaker)**: An administrator API endpoint and UI toggle that instantly freezes all active agent loops and publication adapters across the organization.

---

## 9. 7-Phase Development Roadmap (7–9 Weeks)

| Phase | Timeline | Milestone Name | Status | Deliverables |
| :-: | :--- | :--- | :--- | :--- |
| **Phase 1** | **Week 1** | **Foundation, Architecture & Repository Setup** | **COMPLETED** | Repository initialization, Vite/React container setup, baseline documentation, metadata sync. |
| **Phase 2** | **Week 2** | **Local Data Plane & Processing Engines** | *PLANNED* | Python worker daemon, Pandas profiler engine, Microsoft Presidio PII scanner integration, local file encryption. |
| **Phase 3** | **Weeks 3–4** | **MCP Server & Bounded Agent Orchestration** | *PLANNED* | Implementation of all 12 MCP tools, custom bounded agent loop, schema validator, stop reason handler. |
| **Phase 4** | **Week 5** | **Cloud Control Plane API & PostgreSQL Ledger** | *PLANNED* | FastAPI backend framework, 13 PostgreSQL entities, Alembic migrations, RBAC enforcement. |
| **Phase 5** | **Weeks 6–7** | **Two-Model Review Architecture & Human Approval UI** | *PLANNED* | Independent Challenger AI model client, React governance dashboard, Presidio evidence visualization, hash-bound approval UI. |
| **Phase 6** | **Week 8** | **Idempotency, Background Jobs & Emergency Pause Switch** | *PLANNED* | APScheduler background monitoring, idempotency key validation, global circuit breaker halt switch. |
| **Phase 7** | **Week 9** | **End-to-End Hardening, Dockerization & Capstone Release** | *PLANNED* | Multi-container Docker Compose orchestration, end-to-end security audit, final capstone verification. |
