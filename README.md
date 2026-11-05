# ReleaseGate — Evidence-Driven AI Data Release Governance Agent

[![ReleaseGate Architecture Baseline](https://img.shields.io/badge/Architecture_Baseline-v1.0_Frozen-blue.svg)](docs/architecture.md)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Implementation_Status-Phase_1:_Foundation_(W1)-amber.svg)](#implementation-status--7-phase-roadmap)

> **Authoritative Baseline Reference**: Detailed architectural specifications, entity relationships, and protocol contracts are documented in [`docs/architecture.md`](docs/architecture.md).

**ReleaseGate** is an evidence-driven, autonomous AI data release governance system designed to evaluate, sanitize, verify, and authorize sensitive dataset releases across enterprise environments. 

Unlike generic conversational AI chatbots, ReleaseGate operates as a **governance agent** — executing bounded, deterministic workflow loops, evaluating structured evidence against organizational compliance policies, running independent multi-model review cycles, and enforcing cryptographic hash-bound human approval before any dataset can be published.

---

## Executive Summary & Core Value Proposition

In modern enterprise data environments, publishing datasets — whether for open source, third-party vendor integration, machine learning training, or cross-departmental sharing — carries high risks of Personally Identifiable Information (PII) leakage, compliance violations (GDPR, HIPAA, CCPA), and unintended data exposure.

ReleaseGate solves this challenge through a **hybrid governance model**:
* **Local Data Processing Plane**: Keeps raw, sensitive datasets entirely within the local execution environment. Raw data **never** leaves local processing by default.
* **Cloud Control Plane**: Manages release governance policies, ingests sanitized metadata evidence, coordinates AI reviewer evaluations, tracks tamper-evident audit logs, and hosts human-in-the-loop approval workflows.

---

## Core Operating Principles

1. **AI Recommends, Humans Authorize**: AI can investigate, analyze, and recommend remediation, but AI can **never** independently authorize a release. Every publication requires explicit human authorization.
2. **Version-Bound Authorization**: Authorization applies to an **exact dataset content hash** (`proposed_output_hash`), not merely a dataset name or release request ID.
3. **Two-Model Review Architecture**: An independent AI reviewer ("Challenger") must audit and challenge the primary agent's ("Investigator") remediation proposal.
4. **Local Data Isolation**: Original datasets and raw sensitive source files must remain strictly inside the local processing environment.
5. **Auditable & Idempotent Execution**: Every tool execution is recorded in an append-only audit ledger. Repeated requests with identical idempotency keys cannot create duplicate operations.
6. **Immediate Emergency Halt**: Administrators must be able to halt all execution instantly via a global pause switch (circuit breaker).
7. **Fail-Closed Execution**: Missing evidence, checksum mismatches, tool timeouts, or policy violations automatically halt the pipeline.

---

## Technology Stack

The ReleaseGate architecture relies on industry-standard, production-grade frameworks across both planes:

| Operating Layer | Technology Selection | Purpose |
| :--- | :--- | :--- |
| **Control Plane Frontend** | **React 19**, **TypeScript**, **Vite**, **Tailwind CSS**, **shadcn/ui**, **Lucide Icons**, **Motion** | Real-time release governance dashboard, evidence viewer, human approval queue |
| **Control Plane API** | **Python 3.11+**, **FastAPI**, **Uvicorn**, **Pydantic v2** | RESTful API gateway, RBAC, approval management, job coordination |
| **Database & Audit Ledger** | **PostgreSQL**, **SQLAlchemy 2.0**, **Alembic** | Relational state machine, 13 core database entities, append-only audit log |
| **Agent Orchestration** | **Custom Bounded Agent Loop** | Bounded reasoning budget (12 tools, 8 reasoning steps, 1 controlled rewrite, 3 execution retries) |
| **Tool Communication** | **Model Context Protocol (MCP)** | Typed JSON schema tool interfaces (`mcp-server`) |
| **Local Data Engines** | **Python (Pandas & Microsoft Presidio)** | Tabular profiling, named-entity recognition (PII detection), anonymization |
| **AI Reviewer** | **Independent Model Client** | Secondary model session ("Challenger") to audit primary findings |
| **Job Scheduling** | **APScheduler** | Recurring background audit tasks, policy timers, approval expirations |
| **Deployment Packaging** | **Docker & Docker Compose** | Standardized containers for control plane and local worker nodes |

---

## Architecture Overview & Network Boundaries

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

### Strict Data Isolation Rules
1. **Raw Datasets Stay Local**: Raw files and unmasked PII records **never** leave local processing by default.
2. **Sanitized Evidence Transmission**: Only non-sensitive metadata, PII entity count histograms, risk scores, sanitized evidence snippets, and SHA-256 hashes are sent to the cloud.
3. **Outbound Communication**: The local worker initiates outbound authenticated HTTPS calls to the cloud API. The local MCP server is never exposed directly to the public internet.

---

## Detailed 9-Step Governance Request Flow

```
[1. User Request in Web Dashboard]
       |
       v
[2. FastAPI Auth/RBAC & Job Coordinator]
       |
       v
[3. Signed Job Request Sent to Local Worker]
       |
       v
[4. Local Worker Runs Bounded Agent Loop (Primary Model + Local MCP Server)]
       |
       v
[5. MCP Server Executes Tools (inspect_dataset, detect_sensitive_data, etc.)]
       |
       v
[6. Independent Reviewer Challenges Report -> Sends Decision to API & Approval Queue]
       |
       v
[7. Human Steward Sign-off -> API Issues Signed Approved Command to Local Worker]
       |
       v
[8. Local Worker Calls MCP Publication Tool -> Verifies Output Hash]
       |
       v
[9. Audit Event Ledger Recorded in PostgreSQL]
```

---

## Bounded Agent Orchestration & Execution Limits

To ensure safety and predictability in safety-critical governance tasks, ReleaseGate enforces hard execution boundaries:

### Bounded Execution Budget
* **Maximum 12 tool calls** per investigation run.
* **Maximum 8 reasoning iterations**.
* **Exactly one controlled rewrite** attempt following a reviewer rejection.
* **Up to 3 execution attempts** with exponential backoff.
* **Fixed model timeouts** and monetary/token limits per job.

### Explicit Stop Reasons
Execution halts immediately with an explicit status code upon reaching any boundary:  
`COMPLETED`, `HUMAN_APPROVAL_REQUIRED`, `REVIEW_REJECTED`, `MAX_ITERATIONS_REACHED`, `TOOL_VALIDATION_FAILED`, `MODEL_TIMEOUT`, `POLICY_BLOCKED`, `EXECUTION_FAILED`, `SYSTEM_PAUSED`.

> *A model timeout or missing response is NEVER treated as permission to proceed.*

---

## Model Context Protocol (MCP) Tool Registry (All 12 Tools)

The local MCP server exposes exactly 12 schema-validated tools:

| # | MCP Tool Name | Function & Purpose |
| :-: | :--- | :--- |
| 1 | `inspect_dataset` | Profile dataset schema, column types, row counts, and null distributions. |
| 2 | `detect_sensitive_data` | Execute Microsoft Presidio PII scanning on tabular/text fields. |
| 3 | `validate_data_quality` | Measure structural integrity, completeness, and value distribution anomalies. |
| 4 | `check_release_policy` | Evaluate dataset metadata against organizational governance policies. |
| 5 | `generate_risk_report` | Compute deterministic weighted risk score (0-100) and issue breakdown. |
| 6 | `propose_transformation` | Formulate precise sanitization plan (masking, redaction, hashing, top/bottom coding). |
| 7 | `prepare_release` | Stage sanitized dataset artifact and compute SHA-256 `proposed_output_hash`. |
| 8 | `submit_for_review` | Package sanitized evidence JSON for the independent AI reviewer ("Challenger"). |
| 9 | `get_approval_status` | Check human approval queue state and cryptographic signature validity. |
| 10 | `publish_dataset` | Trigger authorized publication adapter to target destination. |
| 11 | `verify_publication` | Verify target destination receipt, accessibility, and artifact checksum matching. |
| 12 | `withdraw_release` | Cancel or recall an active or pending release request. |

---

## PostgreSQL Database Architecture (All 13 Core Entities)

The Cloud Control Plane stores governance application state in 13 PostgreSQL tables:

```
1. users             - System user accounts, emails, hashed credentials
2. organizations     - Workspace and tenant boundaries
3. memberships       - User roles and permissions (RBAC)
4. datasets          - Top-level dataset entity records
5. dataset_versions  - Immutable dataset version records with content_hash
6. inspection_runs   - Profiler and Presidio execution records & risk scores
7. findings          - Detected PII/quality issues with structured evidence JSONB
8. release_requests  - Release proposals referencing dataset versions and proposed_output_hash
9. review_results    - Independent reviewer evaluations and structured findings
10. approval_requests- Human authorization queue records bound to artifact_hash
11. execution_records- Publication attempt receipts, status, and idempotency_key
12. audit_events     - Append-only activity ledger with event_hash and previous_event_hash
13. scheduled_jobs   - APScheduler jobs for background audits & approval expiration
```

---

## Governance & Security Safeguards

1. **Exact Artifact Hash Binding**: Approvals sign the SHA-256 binary hash (`artifact_hash` / `proposed_output_hash`). Any file modification invalidates the approval token.
2. **Independent Two-Model Review**: A secondary model session ("Challenger") evaluates findings independently using structured JSON validation.
3. **Idempotent Operations**: All execution commands require a unique `idempotency_key` to prevent duplicate publication or execution.
4. **Append-Only Audit Integrity**: Audit events form a cryptographic hash chain. Application users cannot modify or delete audit entries.
5. **Emergency Global Pause Switch (Circuit Breaker)**: Administrators can instantly pause all automated releases system-wide via a global API switch.

---

## Monorepo Directory Structure

```
releasegate/
├── README.md                          # Project documentation & baseline summary
├── docs/                              # Technical specifications & architecture blueprints
│   └── architecture.md                # Authoritative Baseline Architecture Reference
├── metadata.json                      # AI Studio app metadata
├── index.html                         # Web entry point
├── package.json                       # Frontend dependencies & scripts
├── vite.config.ts                     # Vite bundler configuration
├── tsconfig.json                      # TypeScript configuration
├── .env.example                       # Environment template
│
├── apps/                              # Application Layer
│   ├── web/                           # Control Plane Frontend (React 19 + Vite)
│   │   ├── src/                       # Dashboard UI components & views
│   │   └── package.json
│   │
│   └── api/                           # Control Plane Backend (Python + FastAPI)
│       ├── app/                       # Auth, datasets, releases, approvals, audit APIs
│       └── requirements.txt
│
├── agent/                             # Bounded Agent Loop & Orchestrator
├── mcp-server/                        # Local MCP Tool Server (12 Tools)
├── engines/                           # Profiler, Presidio Scanner & Sanitizer
├── local-worker/                      # Local Execution Worker Node
├── shared/                            # Shared Schemas & Contracts
├── tests/                             # Unit, Integration & Security Tests
└── infrastructure/                    # Docker, Alembic Migrations & Configs
```

---

## Implementation Status & 7-Phase Roadmap (7–9 Weeks)

> **IMPORTANT STATUS CLEARITY**: This repository is currently at **Phase 1: Foundation Baseline**. 
> The initial frontend container, build configuration, and architecture documentation have been completed. Application backend services, MCP servers, and data engines are planned for subsequent development phases.

```
[Phase 1: Foundation & Architecture Setup (W1)] <=== (COMPLETED)
       |
       v
[Phase 2: Local Data Plane & Processing Engines (W2)] (PLANNED)
       |
       v
[Phase 3: MCP Tool Server & Bounded Agent Orchestration (W3-4)] (PLANNED)
       |
       v
[Phase 4: FastAPI Control Plane & 13 PostgreSQL Entities (W5)] (PLANNED)
       |
       v
[Phase 5: Two-Model Review Architecture & Human Approval UI (W6-7)] (PLANNED)
       |
       v
[Phase 6: Idempotency, Background Jobs & Circuit Breaker (W8)] (PLANNED)
       |
       v
[Phase 7: End-to-End Hardening, Dockerization & Capstone Release (W9)] (PLANNED)
```

| Phase | Timeline | Phase Name | Status | Key Deliverables & Scope |
| :-: | :--- | :--- | :--- | :--- |
| **Phase 1** | **Week 1** | **Foundation, Architecture & Repository Setup** | **COMPLETED** | Initialized repository container, configured Vite/React 19 stack, metadata sync, created `README.md` and authoritative `docs/architecture.md`. |
| **Phase 2** | **Week 2** | **Local Data Plane & Processing Engines** | *PLANNED* | Python worker daemon, Pandas profiler engine, Microsoft Presidio PII scanner integration, local encrypted file storage. |
| **Phase 3** | **Weeks 3–4** | **MCP Server & Bounded Agent Orchestration** | *PLANNED* | Implement all 12 MCP tools, custom bounded agent loop orchestrator, JSON schema validator, explicit stop reason handlers. |
| **Phase 4** | **Week 5** | **Cloud Control Plane API & PostgreSQL Ledger** | *PLANNED* | FastAPI backend framework, 13 PostgreSQL entities, Alembic migrations, RBAC authorization logic. |
| **Phase 5** | **Weeks 6–7** | **Two-Model Review Architecture & Human Approval UI** | *PLANNED* | Independent Challenger AI reviewer client, React governance dashboard, Presidio evidence visualization, hash-bound human approval UI. |
| **Phase 6** | **Week 8** | **Idempotency, Background Jobs & Circuit Breaker** | *PLANNED* | APScheduler background audit jobs, idempotency key enforcement, global emergency pause switch. |
| **Phase 7** | **Week 9** | **End-to-End Hardening, Dockerization & Capstone Release** | *PLANNED* | Multi-container Docker Compose orchestration, security audit, fail-closed verification, capstone release submission. |

---

## Local Development & Setup Instructions

### Prerequisites
Make sure your system meets the following requirements:
* **Node.js**: v20.0.0 or higher
* **npm**: v10.0.0 or higher
* **Python**: v3.11 or higher *(for upcoming backend & worker services)*
* **Docker & Docker Compose**: *(for PostgreSQL and container orchestration)*

### 1. Repository Setup

```bash
# Clone the ReleaseGate repository
git clone https://github.com/your-username/ReleaseGate.git
cd ReleaseGate

# Install frontend UI dependencies
npm install
```

### 2. Environment Configuration

Copy the template environment file to `.env`:

```bash
cp .env.example .env
```

Ensure `.env` contains key development environment variables:

```env
# Frontend Server
PORT=3000

# Control Plane API (Planned Stack)
FASTAPI_ENV=development
DATABASE_URL=postgresql://releasegate:releasegate_pass@localhost:5432/releasegate_db

# Gemini AI API Key (Required for Primary & Reviewer AI Models)
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Running the Control Plane Web UI

To start the Vite development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Running Backend & Database Infrastructure (Planned Stack)

To start PostgreSQL and control plane containers using Docker Compose:

```bash
# Start PostgreSQL database and FastAPI services
docker-compose -f infrastructure/docker-compose.yml up -d

# Run database migrations
cd apps/api
alembic upgrade head
```

---

## License

Distributed under the Apache 2.0 License. See `LICENSE` for details.

---

*ReleaseGate — Evidence-driven, privacy-focused AI data release governance.*
