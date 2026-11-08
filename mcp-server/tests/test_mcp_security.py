"""
Security-focused MCP tests: strict schemas, session permissions, tenant
isolation, human authorization, data-leak guards, and code/database boundaries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import uuid

import pytest
from mcp.shared.exceptions import McpError
from pydantic import ValidationError

from local_worker.secure_storage import LocalDatasetStorage
from mcp_server.schemas.tools import (
    CheckReleasePolicyArgs,
    DetectSensitiveDataArgs,
    FilterRowsOperation,
    GeneralizeColumnOperation,
    GenerateRiskReportArgs,
    GetApprovalStatusArgs,
    InspectDatasetArgs,
    PrepareReleaseArgs,
    ProposeTransformationArgs,
    PublishDatasetArgs,
    SubmitForReviewArgs,
    TOOL_ARGUMENT_MODELS,
    ValidateDataQualityArgs,
    VerifyPublicationArgs,
    WithdrawReleaseArgs,
)
from mcp_server.security.approvals import HumanApprovalAuthority
from mcp_server.security.permissions import (
    ClientChannel,
    HumanApprovalRequiredError,
    MCPConfigurationError,
    MCPPermissionError,
    MCPPrincipal,
    ToolRole,
    resolve_principal_from_env,
    verify_tool_permission,
)
from mcp_server.security.redaction import (
    DataLeakageError,
    enforce_cloud_safe,
    sanitize_for_audit,
)
from mcp_server.server import create_mcp_server
from mcp_server.service_interface import (
    ReleaseGateService,
    ServiceNotFoundError,
    ServiceValidationError,
)
from mcp_server.tools.registry import TOOL_SPECS

from mcp_support import (
    CLEAN_CSV,
    DIRTY_CSV,
    ORG_A,
    ORG_B,
    call_error,
    call_json,
    make_principal,
    make_server,
    mcp_client,
    prepare_and_submit,
    read_resource,
    seeded,
)

VALID_MODEL_PAYLOADS = {
    "inspect_dataset": {"dataset_id": str(uuid.uuid4()), "version_number": 2},
    "detect_sensitive_data": {
        "dataset_id": str(uuid.uuid4()),
        "confidence_threshold": 0.5,
        "entities": ["EMAIL_ADDRESS", "PHONE_NUMBER"],
    },
    "validate_data_quality": {
        "dataset_id": str(uuid.uuid4()),
        "allow_nulls": False,
        "allow_duplicates": False,
    },
    "check_release_policy": {
        "dataset_id": str(uuid.uuid4()),
        "policy_version": "1.0.0",
        "domain": "internal_analytics",
    },
    "generate_risk_report": {"dataset_id": str(uuid.uuid4())},
    "propose_transformation": {
        "dataset_id": str(uuid.uuid4()),
        "operations": [
            {"operation": "mask_column", "column": "email_address", "strategy": "partial_email"}
        ],
        "rationale": "Mask email addresses before release",
    },
    "prepare_release": {
        "dataset_id": str(uuid.uuid4()),
        "destination_target": "s3://release-evidence/exports",
    },
    "submit_for_review": {
        "dataset_id": str(uuid.uuid4()),
        "staged_release_id": "rel_0123456789ab",
    },
    "get_approval_status": {"release_id": "rel_0123456789ab"},
    "publish_dataset": {
        "release_id": "rel_0123456789ab",
        "approval_id": "apr_" + "a" * 32,
        "expected_artifact_hash": "a" * 64,
    },
    "verify_publication": {"release_id": "rel_0123456789ab"},
    "withdraw_release": {
        "release_id": "rel_0123456789ab",
        "reason": "Withdrawing after an audit finding",
    },
}


# =============================================================================
# Strict Pydantic tool schemas
# =============================================================================
class TestToolSchemas:
    def test_all_twelve_models_validate_valid_arguments(self):
        assert set(TOOL_ARGUMENT_MODELS) == set(VALID_MODEL_PAYLOADS)
        for name, model in TOOL_ARGUMENT_MODELS.items():
            parsed = model.model_validate(VALID_MODEL_PAYLOADS[name])
            assert parsed is not None

    def test_all_schemas_forbid_extra_properties_at_the_root(self):
        for name, model in TOOL_ARGUMENT_MODELS.items():
            schema = model.model_json_schema()
            assert schema.get("additionalProperties") is False, name
            assert schema["type"] == "object", name

    @pytest.mark.parametrize("forbidden", ["caller_role", "organization_id", "role", "approval_token"])
    def test_identity_and_token_injection_is_rejected(self, forbidden):
        for name, model in TOOL_ARGUMENT_MODELS.items():
            with pytest.raises(ValidationError):
                model.model_validate({**VALID_MODEL_PAYLOADS[name], forbidden: "ADMIN"})

    def test_inspect_dataset_constraints(self):
        with pytest.raises(ValidationError):
            InspectDatasetArgs(dataset_id="not-a-uuid")
        with pytest.raises(ValidationError):
            InspectDatasetArgs(dataset_id=str(uuid.uuid4()), version_number=0)
        with pytest.raises(ValidationError):
            InspectDatasetArgs(dataset_id=str(uuid.uuid4()), raw_path="/etc/passwd")

    def test_detect_sensitive_data_constraints(self):
        with pytest.raises(ValidationError):
            DetectSensitiveDataArgs(dataset_id=str(uuid.uuid4()), confidence_threshold=1.5)
        with pytest.raises(ValidationError):
            DetectSensitiveDataArgs(dataset_id=str(uuid.uuid4()), confidence_threshold=-0.1)
        with pytest.raises(ValidationError):
            DetectSensitiveDataArgs(dataset_id=str(uuid.uuid4()), entities=["bad-entity"])
        normalized = DetectSensitiveDataArgs(
            dataset_id=str(uuid.uuid4()), entities=["email_address", "EMAIL_ADDRESS"]
        )
        assert normalized.entities == ["EMAIL_ADDRESS"]

    def test_quality_and_policy_constraints(self):
        with pytest.raises(ValidationError):
            ValidateDataQualityArgs(dataset_id=str(uuid.uuid4()), allow_nulls="yes")
        with pytest.raises(ValidationError):
            CheckReleasePolicyArgs(dataset_id=str(uuid.uuid4()), domain="Internal Analytics")
        with pytest.raises(ValidationError):
            CheckReleasePolicyArgs(dataset_id=str(uuid.uuid4()), policy_version="latest")

    def test_transformation_schema_is_allowlisted(self):
        base = {
            "dataset_id": str(uuid.uuid4()),
            "operations": [{"operation": "mask_column", "column": "email"}],
            "rationale": "Valid remediation rationale",
        }
        ProposeTransformationArgs.model_validate(base)

        with pytest.raises(ValidationError):
            ProposeTransformationArgs.model_validate(
                {
                    **base,
                    "operations": [
                        {
                            "operation": "execute_python",
                            "column": "email",
                            "code": "import os; os.system('rm -rf /')",
                        }
                    ],
                }
            )
        with pytest.raises(ValidationError):
            ProposeTransformationArgs.model_validate(
                {
                    **base,
                    "operations": [
                        {"operation": "remove_column", "column": "email", "parameters": {}}
                    ],
                }
            )
        with pytest.raises(ValidationError):
            ProposeTransformationArgs.model_validate({**base, "operations": []})
        with pytest.raises(ValidationError):
            ProposeTransformationArgs.model_validate(
                {**base, "operations": [{"operation": "remove_column", "column": "a/b"}]}
            )

        with pytest.raises(ValidationError):
            GeneralizeColumnOperation(
                operation="generalize_column",
                column="age",
                strategy="numeric_binning",
                bins=[10, 5, 20],
            )
        with pytest.raises(ValidationError):
            FilterRowsOperation(operation="filter_rows", column="age", operator="in_list")
        with pytest.raises(ValidationError):
            FilterRowsOperation(operation="filter_rows", column="age", operator="equals")

    def test_release_and_publication_constraints(self):
        with pytest.raises(ValidationError):
            PrepareReleaseArgs(
                dataset_id=str(uuid.uuid4()), destination_target="file:///etc/passwd"
            )
        with pytest.raises(ValidationError):
            PrepareReleaseArgs(
                dataset_id=str(uuid.uuid4()), destination_target="s3://bucket/../secrets"
            )
        with pytest.raises(ValidationError):
            PrepareReleaseArgs(
                dataset_id=str(uuid.uuid4()), destination_target="s3://bucket/export\nrm -rf"
            )
        with pytest.raises(ValidationError):
            SubmitForReviewArgs(
                dataset_id=str(uuid.uuid4()), staged_release_id="stage-1"
            )
        with pytest.raises(ValidationError):
            GetApprovalStatusArgs(release_id="rel_123")
        with pytest.raises(ValidationError):
            PublishDatasetArgs(
                release_id="rel_0123456789ab",
                approval_id="human-token-forged",
                expected_artifact_hash="a" * 64,
            )
        with pytest.raises(ValidationError):
            PublishDatasetArgs(
                release_id="rel_0123456789ab",
                approval_id="apr_" + "a" * 32,
                expected_artifact_hash="not-a-hash",
            )
        with pytest.raises(ValidationError):
            WithdrawReleaseArgs(release_id="rel_0123456789ab", reason="too short")
        with pytest.raises(ValidationError):
            VerifyPublicationArgs(release_id="rel_0123456789ab", destination_target="file:///x")


# =============================================================================
# Session identity and RBAC
# =============================================================================
class TestPermissions:
    def test_role_matrix(self):
        all_tools = set(TOOL_SPECS)
        cases = {
            ToolRole.ADMIN: all_tools,
            ToolRole.STEWARD: all_tools,
            ToolRole.USER: all_tools
            - {"publish_dataset", "verify_publication", "withdraw_release"},
            ToolRole.AUDITOR: {
                "inspect_dataset",
                "detect_sensitive_data",
                "validate_data_quality",
                "check_release_policy",
                "generate_risk_report",
                "get_approval_status",
                "verify_publication",
            },
        }
        for role, allowed in cases.items():
            principal = make_principal(role=role)
            for tool in all_tools:
                if tool in allowed:
                    verify_tool_permission(tool, principal)
                else:
                    with pytest.raises(MCPPermissionError):
                        verify_tool_permission(tool, principal)

    @pytest.mark.asyncio
    async def test_user_role_cannot_publish_or_withdraw(self, seeded):
        async with mcp_client(make_server(seeded, role=ToolRole.USER)) as session:
            publish_message = await call_error(
                session,
                "publish_dataset",
                {
                    "release_id": "rel_0123456789ab",
                    "approval_id": "apr_" + "a" * 32,
                    "expected_artifact_hash": "a" * 64,
                },
            )
            withdraw_message = await call_error(
                session,
                "withdraw_release",
                {"release_id": "rel_0123456789ab", "reason": "Attempting unauthorized withdrawal"},
            )
            inspected = await call_json(session, "inspect_dataset", {"dataset_id": seeded.clean_id})
        assert "Permission denied" in publish_message
        assert "Permission denied" in withdraw_message
        assert inspected["dataset_id"] == seeded.clean_id

    @pytest.mark.asyncio
    async def test_auditor_is_read_only(self, seeded):
        async with mcp_client(make_server(seeded, role=ToolRole.AUDITOR)) as session:
            message = await call_error(
                session,
                "propose_transformation",
                {
                    "dataset_id": seeded.clean_id,
                    "operations": [{"operation": "remove_column", "column": "region_code"}],
                    "rationale": "Auditor should not transform data",
                },
            )
            assert "Permission denied" in message

    @pytest.mark.asyncio
    async def test_tool_arguments_cannot_escalate_role(self, seeded):
        async with mcp_client(make_server(seeded, role=ToolRole.STEWARD)) as session:
            message = await call_error(
                session,
                "inspect_dataset",
                {"dataset_id": seeded.clean_id, "caller_role": "ADMIN"},
            )
        assert "Additional properties are not allowed" in message or "Invalid arguments" in message

    def test_principal_resolution_from_authenticated_environment(self):
        principal = resolve_principal_from_env(
            {
                "RELEASEGATE_MCP_PRINCIPAL_ID": "agent-9",
                "RELEASEGATE_MCP_ORGANIZATION_ID": ORG_A,
                "RELEASEGATE_MCP_ROLE": "STEWARD",
                "RELEASEGATE_MCP_CHANNEL": "AI_AGENT",
            }
        )
        assert principal.principal_id == "agent-9"
        assert principal.organization_id == ORG_A
        assert principal.role is ToolRole.STEWARD
        assert principal.channel is ClientChannel.AI_AGENT

    @pytest.mark.parametrize(
        "environment",
        [
            {},
            {"RELEASEGATE_MCP_PRINCIPAL_ID": "a", "RELEASEGATE_MCP_ROLE": "ADMIN"},
            {
                "RELEASEGATE_MCP_PRINCIPAL_ID": "a",
                "RELEASEGATE_MCP_ORGANIZATION_ID": ORG_A,
                "RELEASEGATE_MCP_ROLE": "OWNER",
            },
            {
                "RELEASEGATE_MCP_PRINCIPAL_ID": "a",
                "RELEASEGATE_MCP_ORGANIZATION_ID": "bad org!",
                "RELEASEGATE_MCP_ROLE": "ADMIN",
            },
            {
                "RELEASEGATE_MCP_PRINCIPAL_ID": "a",
                "RELEASEGATE_MCP_ORGANIZATION_ID": ORG_A,
                "RELEASEGATE_MCP_ROLE": "ADMIN",
                "RELEASEGATE_MCP_CHANNEL": "ROBOT",
            },
        ],
    )
    def test_incomplete_or_invalid_identity_fails_closed(self, environment):
        with pytest.raises(MCPConfigurationError):
            resolve_principal_from_env(environment)

    def test_server_refuses_to_start_without_identity(self, monkeypatch, seeded):
        for variable in (
            "RELEASEGATE_MCP_PRINCIPAL_ID",
            "RELEASEGATE_MCP_ORGANIZATION_ID",
            "RELEASEGATE_MCP_ROLE",
            "RELEASEGATE_MCP_CHANNEL",
        ):
            monkeypatch.delenv(variable, raising=False)
        with pytest.raises(MCPConfigurationError):
            create_mcp_server(service=seeded.service)


# =============================================================================
# Organization isolation
# =============================================================================
class TestOrganizationIsolation:
    @pytest.mark.asyncio
    async def test_other_organization_cannot_read_tools_or_resources(self, seeded):
        async with mcp_client(make_server(seeded, organization_id=ORG_B)) as session:
            inspect_message = await call_error(
                session, "inspect_dataset", {"dataset_id": seeded.dirty_id}
            )
            policy_message = await call_error(
                session, "check_release_policy", {"dataset_id": seeded.dirty_id}
            )
            with pytest.raises(McpError) as resource_error:
                await session.read_resource(
                    f"releasegate://datasets/{seeded.dirty_id}/profile"
                )
        assert "Dataset version not found for this organization" in inspect_message
        assert "Dataset version not found for this organization" in policy_message
        # Same generic message for a genuinely missing dataset (no existence oracle).
        assert "Dataset version not found for this organization" in str(resource_error.value)

    @pytest.mark.asyncio
    async def test_same_dataset_uuid_is_isolated_per_organization(self, seeded):
        seeded.service.register_dataset_artifact(
            organization_id=ORG_B,
            dataset_id=seeded.dirty_id,
            content=CLEAN_CSV,
            name="Other tenant dataset",
        )
        async with mcp_client(make_server(seeded, organization_id=ORG_A)) as org_a_session:
            profile_a = await read_resource(
                org_a_session, f"releasegate://datasets/{seeded.dirty_id}/profile"
            )
        async with mcp_client(make_server(seeded, organization_id=ORG_B)) as org_b_session:
            profile_b = await read_resource(
                org_b_session, f"releasegate://datasets/{seeded.dirty_id}/profile"
            )
            inspect_b = await call_json(
                org_b_session, "inspect_dataset", {"dataset_id": seeded.dirty_id}
            )
        assert profile_a["content_hash"] != profile_b["content_hash"]
        assert profile_a["profile"]["row_count"] == 5
        assert profile_b["profile"]["row_count"] == 3
        assert inspect_b["findings_count"] == 0

    @pytest.mark.asyncio
    async def test_release_lifecycle_is_organization_scoped(self, seeded):
        async with mcp_client(make_server(seeded, organization_id=ORG_A)) as session_a:
            submitted = await prepare_and_submit(session_a, seeded.clean_id)
            approval = seeded.service.record_human_approval(
                organization_id=ORG_A,
                release_id=submitted["release_id"],
                artifact_hash=submitted["artifact_hash"],
                approver_id="human-steward-1",
            )

        async with mcp_client(make_server(seeded, organization_id=ORG_B)) as session_b:
            for tool, arguments in (
                (
                    "get_approval_status",
                    {"release_id": submitted["release_id"]},
                ),
                (
                    "publish_dataset",
                    {
                        "release_id": submitted["release_id"],
                        "approval_id": approval.approval_id,
                        "expected_artifact_hash": submitted["artifact_hash"],
                    },
                ),
                (
                    "verify_publication",
                    {"release_id": submitted["release_id"]},
                ),
                (
                    "withdraw_release",
                    {
                        "release_id": submitted["release_id"],
                        "reason": "Cross-tenant withdrawal attempt",
                    },
                ),
            ):
                message = await call_error(session_b, tool, arguments)
                assert "Release not found for this organization" in message, tool

            with pytest.raises(McpError):
                await session_b.read_resource(
                    f"releasegate://releases/{submitted['release_id']}/evidence"
                )

    def test_service_rejects_cross_organization_lookup_directly(self, seeded):
        with pytest.raises(ServiceNotFoundError):
            seeded.service.get_dataset_profile(
                organization_id=ORG_B, dataset_id=seeded.dirty_id
            )
        with pytest.raises(ServiceNotFoundError):
            seeded.service.get_release_evidence(
                organization_id=ORG_B, release_id="rel_0123456789ab"
            )


# =============================================================================
# Human authorization and publication
# =============================================================================
class TestHumanAuthorization:
    @pytest.mark.asyncio
    async def test_publication_requires_review_and_human_approval(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            prepared = await call_json(
                session,
                "prepare_release",
                {"dataset_id": seeded.clean_id, "destination_target": "s3://release-evidence/exports"},
            )
            release_id = prepared["release_id"]

            not_reviewed = await call_error(
                session,
                "publish_dataset",
                {
                    "release_id": release_id,
                    "approval_id": "apr_" + "a" * 32,
                    "expected_artifact_hash": prepared["artifact_hash"],
                },
            )
            assert "submitted for review" in not_reviewed

            await call_json(
                session,
                "submit_for_review",
                {"dataset_id": seeded.clean_id, "staged_release_id": release_id},
            )
            no_approval = await call_error(
                session,
                "publish_dataset",
                {
                    "release_id": release_id,
                    "approval_id": "apr_" + "a" * 32,
                    "expected_artifact_hash": prepared["artifact_hash"],
                },
            )
        assert "Human authorization required" in no_approval

    @pytest.mark.asyncio
    async def test_ai_cannot_create_or_mint_approvals(self, seeded):
        names = set(TOOL_SPECS)
        assert "record_human_approval" not in names
        assert not any("approve" in name or "authorize" in name for name in names)
        publish_schema = TOOL_SPECS["publish_dataset"].args_model.model_json_schema()
        assert "approval_token" not in publish_schema["properties"]

        authority = HumanApprovalAuthority()
        with pytest.raises(HumanApprovalRequiredError):
            authority.record_human_approval(
                release_id="rel_0123456789ab",
                artifact_hash="a" * 64,
                organization_id=ORG_A,
                approver_id="model:self",
                approver_type="AI",
            )

    @pytest.mark.asyncio
    async def test_approval_must_bind_to_the_exact_release_and_hash(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            first = await prepare_and_submit(session, seeded.clean_id)
            second = await call_json(
                session,
                "prepare_release",
                {"dataset_id": seeded.clean_id, "destination_target": "gcs://release-evidence/second"},
            )
            await call_json(
                session,
                "submit_for_review",
                {"dataset_id": seeded.clean_id, "staged_release_id": second["release_id"]},
            )
            approval_for_first = seeded.service.record_human_approval(
                organization_id=ORG_A,
                release_id=first["release_id"],
                artifact_hash=first["artifact_hash"],
                approver_id="human-steward-1",
            )
            message = await call_error(
                session,
                "publish_dataset",
                {
                    "release_id": second["release_id"],
                    "approval_id": approval_for_first.approval_id,
                    "expected_artifact_hash": second["artifact_hash"],
                },
            )
        assert "does not match this release and artifact" in message

    @pytest.mark.asyncio
    async def test_wrong_artifact_hash_is_rejected(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            submitted = await prepare_and_submit(session, seeded.clean_id)
            approval = seeded.service.record_human_approval(
                organization_id=ORG_A,
                release_id=submitted["release_id"],
                artifact_hash=submitted["artifact_hash"],
                approver_id="human-steward-1",
            )
            message = await call_error(
                session,
                "publish_dataset",
                {
                    "release_id": submitted["release_id"],
                    "approval_id": approval.approval_id,
                    "expected_artifact_hash": "f" * 64,
                },
            )
        assert "Artifact hash mismatch" in message

    @pytest.mark.asyncio
    async def test_expired_approval_cannot_publish(self, tmp_path):
        clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        authority = HumanApprovalAuthority(ttl_seconds=60, clock=lambda: clock[0])
        service = ReleaseGateService(
            storage=LocalDatasetStorage(base_dir=tmp_path),
            approval_authority=authority,
            pseudonym_secret="expiry-test-secret",
        )
        dataset_id = "33333333-3333-4333-8333-333333333333"
        service.register_dataset_artifact(
            organization_id=ORG_A, dataset_id=dataset_id, content=CLEAN_CSV
        )
        server = create_mcp_server(service=service, principal=make_principal())
        async with mcp_client(server) as session:
            submitted = await prepare_and_submit(session, dataset_id)
            approval = service.record_human_approval(
                organization_id=ORG_A,
                release_id=submitted["release_id"],
                artifact_hash=submitted["artifact_hash"],
                approver_id="human-steward-1",
            )
            clock[0] = clock[0] + timedelta(seconds=61)
            message = await call_error(
                session,
                "publish_dataset",
                {
                    "release_id": submitted["release_id"],
                    "approval_id": approval.approval_id,
                    "expected_artifact_hash": submitted["artifact_hash"],
                },
            )
        assert "expired or was revoked" in message

    def test_approval_requires_completed_review_and_eligible_release(self, seeded):
        service = seeded.service
        prepared = service.prepare_release(
            organization_id=ORG_A,
            dataset_id=seeded.clean_id,
            destination_target="s3://release-evidence/exports",
        )
        with pytest.raises(ServiceValidationError):
            service.record_human_approval(
                organization_id=ORG_A,
                release_id=prepared["release_id"],
                artifact_hash=prepared["artifact_hash"],
                approver_id="human-steward-1",
            )

        dirty = service.prepare_release(
            organization_id=ORG_A,
            dataset_id=seeded.dirty_id,
            destination_target="s3://release-evidence/exports",
        )
        service.submit_for_review(
            organization_id=ORG_A,
            dataset_id=seeded.dirty_id,
            staged_release_id=dirty["release_id"],
        )
        with pytest.raises(ServiceValidationError):
            service.record_human_approval(
                organization_id=ORG_A,
                release_id=dirty["release_id"],
                artifact_hash=dirty["artifact_hash"],
                approver_id="human-steward-1",
            )

    @pytest.mark.asyncio
    async def test_approval_identifier_is_not_exposed_to_the_model(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            submitted = await prepare_and_submit(session, seeded.clean_id)
            approval = seeded.service.record_human_approval(
                organization_id=ORG_A,
                release_id=submitted["release_id"],
                artifact_hash=submitted["artifact_hash"],
                approver_id="human-steward-1",
            )
            status = await call_json(
                session, "get_approval_status", {"release_id": submitted["release_id"]}
            )
        serialized = json.dumps(status)
        assert status["is_approved"] is True
        assert status["approval"]["approver_id"] == "human-steward-1"
        assert approval.approval_id not in serialized

    @pytest.mark.asyncio
    async def test_withdrawal_revokes_human_approval(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            submitted = await prepare_and_submit(session, seeded.clean_id)
            approval = seeded.service.record_human_approval(
                organization_id=ORG_A,
                release_id=submitted["release_id"],
                artifact_hash=submitted["artifact_hash"],
                approver_id="human-steward-1",
            )
            await call_json(
                session,
                "withdraw_release",
                {
                    "release_id": submitted["release_id"],
                    "reason": "Withdrawing after the steward found a licensing issue",
                },
            )
            with pytest.raises(HumanApprovalRequiredError):
                seeded.service._approvals.verify(
                    approval_id=approval.approval_id,
                    release_id=submitted["release_id"],
                    artifact_hash=submitted["artifact_hash"],
                    organization_id=ORG_A,
                )

    def test_service_rejects_unknown_transformation_operations(self, seeded):
        # Defence in depth: even a caller that bypasses the MCP schema cannot ask
        # the service to execute arbitrary operations.
        with pytest.raises(ServiceValidationError):
            seeded.service.propose_transformation(
                organization_id=ORG_A,
                dataset_id=seeded.dirty_id,
                operations=[{"operation": "execute_sql", "column": "email_address"}],
                rationale="Attempting arbitrary code",
            )


# =============================================================================
# Cloud-safety guard
# =============================================================================
class TestCloudSafetyGuard:
    @pytest.mark.parametrize(
        "payload",
        [
            {"raw_data": [{"email": "x@y.com"}]},
            {"message": "contact alice@example.com"},
            {"message": "call 555-010-1234"},
            {"message": "ssn 123-45-6789"},
            {"message": "read /etc/passwd"},
            {"message": "card 4111 1111 1111 1111"},
        ],
    )
    def test_guard_blocks_raw_or_sensitive_payloads(self, payload):
        with pytest.raises(DataLeakageError):
            enforce_cloud_safe(payload)

    def test_guard_allows_hashes_identifiers_and_aggregates(self):
        payload = {
            "artifact_hash": "a3cde11716c6733713ed1019f5cab7c95eb09b14b2d341fd47754251d05b3d92",
            "dataset_id": "11111111-1111-4111-8111-111111111111",
            "row_count": 5,
            "null_percentages": {"email": 0.0},
        }
        assert enforce_cloud_safe(payload) == payload

    def test_audit_sanitizer_removes_secrets_and_pii(self):
        sanitized = sanitize_for_audit(
            {
                "approval_token": "human-token-secret",
                "expected_artifact_hash": "a" * 64,
                "reason": "contact alice@example.com at /tmp/data.csv",
                "raw_rows": [[1, 2]],
            }
        )
        assert sanitized["approval_token"] == "[REDACTED_SECRET]"
        assert sanitized["expected_artifact_hash"] == "a" * 64
        assert "alice@example.com" not in json.dumps(sanitized)
        assert "/tmp/data.csv" not in json.dumps(sanitized)
        assert sanitized["raw_rows"] == "[REDACTED_RAW_CONTENT]"


# =============================================================================
# Database / filesystem / code-execution boundary
# =============================================================================
class TestMCPBoundary:
    def _mcp_source_files(self):
        mcp_dir = Path(__file__).resolve().parent.parent
        repo_root = mcp_dir.parent
        files = [mcp_dir / "server.py"]
        for folder in ("tools", "resources", "prompts", "schemas", "security"):
            files.extend((mcp_dir / folder).glob("*.py"))
        return repo_root, mcp_dir, files

    def test_only_service_interface_touches_storage_or_database(self):
        repo_root, mcp_dir, files = self._mcp_source_files()
        prohibited = (
            "sqlalchemy",
            "psycopg2",
            "sqlite3",
            "app.db",
            "subprocess",
            "os.system",
        )
        for path in files:
            if path.name == "service_interface.py":
                continue
            text = path.read_text(encoding="utf-8")
            for token in prohibited:
                assert token not in text, f"{path} must not reference {token}"
            assert "LocalDatasetStorage" not in text
            assert "read_dataset" not in text
            assert "store_dataset" not in text

    def test_mcp_layer_never_evaluates_code_or_opens_paths(self):
        _repo_root, _mcp_dir, files = self._mcp_source_files()
        for path in files:
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"(?<![\w.])eval\(", text), path
            assert not re.search(r"(?<![\w.])exec\(", text), path
            assert "open(" not in text, path
            assert "pathlib" not in text, path
            for filesystem_api in (
                "os.path",
                "os.open",
                "os.listdir",
                "os.walk",
                "os.remove",
                "os.unlink",
                "shutil.",
            ):
                assert filesystem_api not in text, f"{path} must not use {filesystem_api}"
