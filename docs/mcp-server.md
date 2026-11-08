# ReleaseGate MCP Server

Status: implemented in [`mcp-server/`](../mcp-server) on the official Python MCP
SDK (`mcp==1.30.0`, low-level `mcp.server.lowlevel.Server`, stdio transport).

The server is the local data-plane interface for AI assistants. It exposes exactly
12 tools, 4 resources, and 4 prompts. It reads datasets locally, returns sanitized
evidence, and cannot authorize publication.

## Architecture

```
MCP client (AI agent / orchestrator)
        |
        | stdio JSON-RPC
        v
mcp-server/                         strict schemas, RBAC, redaction, audit
  server.py  ->  tools/*            one dispatch point for every call
  resources/ prompts/
        |
        v
mcp-server/service_interface.py     the only MCP file with storage/engine access
        |
        +--> local-worker/secure_storage.py
        +--> engines/ (profiler, PII, quality, policy, transformations)
```

- Tool handlers never open paths, query a database, or execute code.
- The service composes the local engines directly; it does not import the FastAPI
  or SQLAlchemy control plane.
- Every tool result and resource document passes `enforce_cloud_safe` before it is
  returned. Raw cell values are never included.

## Installation

The MCP plane has a newer Pydantic requirement than the cloud control plane. Use
a dedicated virtual environment; do not combine both requirement sets.

```bash
python3 -m venv .venv-mcp
. .venv-mcp/bin/activate
pip install -r mcp-server/requirements.txt

# Optional but recommended for person/name NER. Without it the PII detector
# falls back to deterministic patterns only.
python -m spacy download en_core_web_sm
```

Run from the repository root so local artifact storage resolves to
`storage/raw_datasets`. Launch the server with:

```bash
python -m mcp_server.server
```

`python -m mcp-server.server` is not valid because the directory name contains a
hyphen; the `mcp_server` package bridges it.

### MCP client configuration

```json
{
  "mcpServers": {
    "releasegate": {
      "command": "/absolute/path/to/.venv-mcp/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/ReleaseGate",
      "env": {
        "RELEASEGATE_MCP_PRINCIPAL_ID": "agent-release-01",
        "RELEASEGATE_MCP_ORGANIZATION_ID": "org-alpha",
        "RELEASEGATE_MCP_ROLE": "USER",
        "RELEASEGATE_MCP_CHANNEL": "AI_AGENT"
      }
    }
  }
}
```

The server writes logs to stderr; stdout belongs to the stdio transport.

## Session identity

Identity is resolved from the launch environment **before** the server starts.
It is never a tool argument. A caller cannot supply `caller_role`,
`organization_id`, or `principal_id` to change its scope; unknown arguments are
rejected by the strict schemas.

| Variable | Required | Meaning |
| --- | --- | --- |
| `RELEASEGATE_MCP_PRINCIPAL_ID` | yes | Authenticated agent/operator identity |
| `RELEASEGATE_MCP_ORGANIZATION_ID` | yes | Tenant scope for every dataset and release |
| `RELEASEGATE_MCP_ROLE` | yes | `ADMIN`, `STEWARD`, `AUDITOR`, or `USER` |
| `RELEASEGATE_MCP_CHANNEL` | no | `AI_AGENT` (default) or `HUMAN_OPERATOR` |
| `RELEASEGATE_APPROVAL_TTL_SECONDS` | no | Human approval lifetime; default `900`, minimum `1` |
| `RELEASEGATE_PSEUDONYMIZATION_SECRET` | no | Stable HMAC key for pseudonymization; random per process if unset |

Startup fails closed (exit code `2`) when identity, organization, or role is
missing or invalid. Run one process per tenant/role; do not reuse a process for
multiple principals.

## Tools (12, frozen)

All argument models are frozen Pydantic models with `extra="forbid"`,
`StrictInt`/`StrictFloat`/`StrictBool` scalars, bounded strings, and UUID parsing.
Unknown fields, wrong types, and out-of-range values are rejected before a
service method runs.

| # | Tool | Arguments | Roles |
| --- | --- | --- | --- |
| 1 | `inspect_dataset` | `dataset_id: UUID`, `version_number=1` | USER, AUDITOR, STEWARD, ADMIN |
| 2 | `detect_sensitive_data` | `dataset_id`, `version_number=1`, `confidence_threshold=0.6` (0–1), `entities` (optional Presidio allowlist) | USER, AUDITOR, STEWARD, ADMIN |
| 3 | `validate_data_quality` | `dataset_id`, `version_number=1`, `allow_nulls` (optional), `allow_duplicates` (optional) | USER, AUDITOR, STEWARD, ADMIN |
| 4 | `check_release_policy` | `dataset_id`, `version_number=1`, `policy_version="1.0.0"`, `domain` (optional `[a-z][a-z0-9_]*`) | USER, AUDITOR, STEWARD, ADMIN |
| 5 | `generate_risk_report` | `dataset_id`, `version_number=1`, `policy_version="1.0.0"` | USER, AUDITOR, STEWARD, ADMIN |
| 6 | `propose_transformation` | `dataset_id`, `version_number=1`, `operations` (1–20), `rationale` (5–1000 chars) | USER, STEWARD, ADMIN |
| 7 | `prepare_release` | `dataset_id`, `source_version_number=1`, `destination_target` (approved URI), `release_notes` (optional) | USER, STEWARD, ADMIN |
| 8 | `submit_for_review` | `dataset_id`, `version_number=1`, `staged_release_id` (optional `rel_…`), `reviewer_notes` (optional) | USER, STEWARD, ADMIN |
| 9 | `get_approval_status` | `release_id` (`rel_` + 12 lowercase hex) | USER, AUDITOR, STEWARD, ADMIN |
| 10 | `publish_dataset` | `release_id`, `approval_id` (`apr_` + 32 lowercase hex), `expected_artifact_hash` (SHA-256 hex) | STEWARD, ADMIN |
| 11 | `verify_publication` | `release_id`, `destination_target` (optional approved URI) | AUDITOR, STEWARD, ADMIN |
| 12 | `withdraw_release` | `release_id`, `reason` (10–500 chars) | STEWARD, ADMIN |

`ADMIN` and `STEWARD` currently have the same MCP tool set; administrative
control-plane actions are outside the MCP surface. `USER` cannot publish,
verify, or withdraw. `AUDITOR` is read-only except for publication verification.

### Approved destinations

`destination_target` must use `s3://`, `gcs://`, `bigquery://`, `sftp://`, or
`internal://`. Local paths (`file:///…`), whitespace/control characters, and
`..` path segments are rejected. Filesystem paths are never tool arguments.

### Transformations

Operations are a discriminated union of five declarative steps. There is no
SQL, shell, expression language, or arbitrary parameter bag:

- `remove_column` — `column`
- `mask_column` — `column`, `strategy` (`full_redaction`, `partial_email`,
  `partial_phone`, `last_4_visible`, `custom_placeholder`), `placeholder`
- `pseudonymize_column` — `column`, `prefix`
- `generalize_column` — `column`, `strategy` (`numeric_binning`,
  `date_truncation`, `category_bucketing`) plus strategy parameters
- `filter_rows` — `column`, allowlisted `operator`, `value` or `values_list`

`propose_transformation` simulates the ordered operations, returns aggregate
impact and a simulated output hash, and does not modify the original artifact.

## Resources (4, frozen)

| URI | Contents |
| --- | --- |
| `releasegate://policies/current` | Policy id/version, weights, risk bands, critical rules, human-authorization rules |
| `releasegate://datasets/{dataset_id}/profile` | Sanitized schema, null, cardinality, and size profile |
| `releasegate://releases/{release_id}/evidence` | Hash-bound release evidence, risk assessment, approval descriptions, provenance timestamps |
| `releasegate://system/status` | Health, plane isolation, and engine versions |

Dataset and release URIs are resolved inside the session's organization. A
lookup for another tenant returns the same generic "not found" response as a
missing record. Approvals are described without their opaque identifier or
verification digest.

## Prompts (4, frozen)

| Prompt | Arguments | Purpose |
| --- | --- | --- |
| `triage_dataset` | `dataset_id`, `version_number` (optional) | Inspect a dataset and classify release readiness |
| `investigate_findings` | `dataset_id`, `version_number` (optional) | Correlate PII and quality findings without raw values |
| `propose_remediation` | `dataset_id`, `version_number` (optional) | Build an allowlisted transformation proposal |
| `challenger_review` | `release_id` | Independent, advisory pre-approval evidence review |

Prompts are guidance text only. They cannot execute tools, change permissions,
or create approvals. The Challenger output is explicitly advisory.

## Human publication authorization

Publication is a two-channel operation. The MCP session can prepare, submit, and
publish, but it cannot create the authorization it needs.

1. `prepare_release` stages the artifact and records its SHA-256 hash, risk score,
   and policy evidence. Staging alone publishes nothing.
2. `submit_for_review` moves the release to `PENDING_REVIEW`.
3. A human steward reviews the evidence out of band. The trusted control plane
   calls `ReleaseGateService.record_human_approval(...)` with the organization,
   release id, exact artifact hash, and human approver id. That method is not an
   MCP tool and rejects non-`HUMAN` approver types. It returns an opaque
   `apr_<32 hex>` approval id bound to that release, hash, and organization, with
   an expiry (default 15 minutes) and an HMAC integrity digest.
4. The orchestrator passes the approval id to `publish_dataset` together with the
   expected artifact hash. The service verifies the record's integrity, binding,
   organization, expiry/revocation, release status, eligibility, and hash before
   transitioning to `PUBLISHED`. The lifecycle lock covers verification and the
   state transition, so a concurrent withdrawal cannot interleave.
5. `verify_publication` reports the publication state and hash integrity;
   `withdraw_release` revokes any outstanding approval and records the mandatory
   reason.

The model cannot mint, guess, or inspect an approval id from tool output. Treat
the id as a short-lived bearer credential: provide it only to the orchestrator
that will perform the authorized publication.

## Error behavior

- Missing/invalid session identity: server refuses to start.
- Unknown tool, malformed arguments, or extra fields: JSON-RPC error; no business
  logic runs.
- Unauthorized tool/resource for the bound role: permission error.
- Missing dataset/release or cross-tenant lookup: generic not found.
- Policy-blocked or unapproved publication: validation/permission error.
- Output that appears to contain raw data or secrets: `DataLeakageError`; the
  response is replaced by a generic refusal rather than leaking the payload.
- Audit entries are bounded, sanitized, and never include raw rows, tokens, or
  approval ids.

## Testing

```bash
# MCP plane only; no DATABASE_URL, FastAPI, or PostgreSQL needed
python -m pytest mcp-server/tests -q

# API-plane integration affected by the shared local-worker bridge
DATABASE_URL="sqlite:///:memory:" ENVIRONMENT=testing \
  python -m pytest apps/api/tests/test_dataset_ingestion.py \
  apps/api/tests/test_hybrid_isolation.py \
  apps/api/tests/test_inspection_workflow.py -q
```

The MCP suite uses a real in-memory MCP client/server session and also launches
the server over stdio, rather than calling handlers directly. It covers:

- exact 12-tool/4-resource/4-prompt registries and strict valid/invalid arguments;
- role permissions, including a `USER` denied publication;
- organization isolation for datasets, releases, and resources;
- the full prepare → submit → publish → verify → withdraw lifecycle;
- forged, expired, revoked, wrong-hash, wrong-org, and brute-force approvals;
- sanitized tool/resource output, with a raw-value leak detector;
- static boundary checks (no storage, database, subprocess, `eval`/`exec`, or
  arbitrary path access outside `service_interface.py`).

## Known limitations

- Dataset, release, and approval registries are in-process. Running
  `python -m mcp_server.server` starts with an empty registry, so artifacts must
  be registered through the trusted local-worker path. To share state, embed the
  server with `create_mcp_server(service=..., principal=...)` after
  `register_dataset_artifact(...)`, or supply persistent adapters behind
  `DatasetStoragePort` and the service's registries. State does not survive a
  restart today.
- `publish_dataset` performs the authorized lifecycle transition and evidence
  check. Transferring bytes to an external destination is left to the trusted
  local-worker/control-plane adapter and is not implemented in this layer.
- `verify_publication` verifies recorded publication state and hash consistency,
  not a remote object store's checksum.
- The MCP server binds one principal per process. Launch separate processes for
  different tenants or roles.
- Presidio's full NER requires a spaCy model. Without `en_core_web_sm` the
  detector logs a warning and uses deterministic pattern recognizers only.
- The MCP and API planes use incompatible Pydantic pins in this repository and
  must run in separate virtual environments.
