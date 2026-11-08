"""
MCP protocol integration tests for the ReleaseGate server.

These tests speak the real MCP protocol over the SDK's in-memory transport, so
they exercise tool listing, JSON-Schema validation, Pydantic validation, RBAC,
resources, prompts, and sanitized outputs exactly as a client would.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError

from mcp_server.security.audit import audit_logger
from mcp_server.tools.registry import TOOL_SPECS

from mcp_support import (
    DIRTY_CSV,
    ORG_A,
    RAW_VALUES,
    call_error,
    call_json,
    call_tool,
    make_server,
    mcp_client,
    names,
    payload,
    prepare_and_submit,
    read_resource,
    seeded,
)

FROZEN_TOOL_NAMES = [
    "inspect_dataset",
    "detect_sensitive_data",
    "validate_data_quality",
    "check_release_policy",
    "generate_risk_report",
    "propose_transformation",
    "prepare_release",
    "submit_for_review",
    "get_approval_status",
    "publish_dataset",
    "verify_publication",
    "withdraw_release",
]


# =============================================================================
# Real stdio launch (the transport used by MCP clients)
# =============================================================================
class TestStdioTransport:
    @pytest.mark.asyncio
    async def test_stdio_server_launches_and_lists_frozen_surface(self):
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": str(repo_root),
                "RELEASEGATE_MCP_PRINCIPAL_ID": "agent-stdio",
                "RELEASEGATE_MCP_ORGANIZATION_ID": ORG_A,
                "RELEASEGATE_MCP_ROLE": "AUDITOR",
                "RELEASEGATE_MCP_CHANNEL": "AI_AGENT",
            }
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            cwd=str(repo_root),
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                templates = await session.list_resource_templates()
                prompts = await session.list_prompts()

                assert names(tools.tools) == FROZEN_TOOL_NAMES
                assert len(resources.resources) == 2
                assert len(templates.resourceTemplates) == 2
                assert len(prompts.prompts) == 4

                # The stdio server must enforce the same server-bound RBAC.
                denied = await session.call_tool(
                    "publish_dataset",
                    {
                        "release_id": "rel_0123456789ab",
                        "approval_id": "apr_" + "a" * 32,
                        "expected_artifact_hash": "a" * 64,
                    },
                )
                assert denied.isError is True


# =============================================================================
# Tool registry and schemas exposed over MCP
# =============================================================================
class TestMCPToolRegistry:
    @pytest.mark.asyncio
    async def test_exactly_twelve_frozen_tools_are_exposed(self, seeded):
        server = make_server(seeded)
        async with mcp_client(server) as session:
            listed = await session.list_tools()
        assert names(listed.tools) == FROZEN_TOOL_NAMES
        assert set(TOOL_SPECS) == set(FROZEN_TOOL_NAMES)

    @pytest.mark.asyncio
    async def test_tool_input_schemas_are_closed_objects(self, seeded):
        server = make_server(seeded)
        async with mcp_client(server) as session:
            listed = await session.list_tools()

        for tool in listed.tools:
            assert tool.description
            assert tool.inputSchema["type"] == "object"
            assert tool.inputSchema.get("additionalProperties") is False
            properties = set(tool.inputSchema.get("properties", {}))
            # Identity and tenant scope are server-bound, never tool arguments.
            assert not properties & {
                "organization_id",
                "caller_role",
                "role",
                "principal_id",
                "channel",
            }

        publish_schema = next(t.inputSchema for t in listed.tools if t.name == "publish_dataset")
        assert "approval_token" not in publish_schema["properties"]
        assert "approval_id" in publish_schema["properties"]


# =============================================================================
# All 12 tools over MCP
# =============================================================================
class TestMCPToolExecution:
    @pytest.mark.asyncio
    async def test_tool_1_inspect_dataset(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            result = await call_json(session, "inspect_dataset", {"dataset_id": seeded.clean_id})
        assert result["dataset_id"] == seeded.clean_id
        assert result["risk_score"] >= 0
        assert result["risk_band"] in {"LOW", "MODERATE", "HIGH", "CRITICAL"}
        assert result["is_release_eligible"] is True
        assert result["summary_report"]["privacy_inspection"]["total_findings"] == 0
        assert result["findings_count"] == 0

    @pytest.mark.asyncio
    async def test_tool_2_detect_sensitive_data(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            result = await call_json(
                session,
                "detect_sensitive_data",
                {"dataset_id": seeded.dirty_id, "confidence_threshold": 0.4},
            )
        assert result["total_findings"] > 0
        assert result["has_high_pii"] is True
        assert {"EMAIL_ADDRESS", "PHONE_NUMBER"}.issubset(set(result["detected_entities"]))
        for finding in result["findings"]:
            assert finding["column_name"]
            assert finding["occurrence_count"] >= 1
            assert "evidence_ref" in finding

    @pytest.mark.asyncio
    async def test_tool_3_validate_data_quality(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            result = await call_json(
                session,
                "validate_data_quality",
                {"dataset_id": seeded.dirty_id, "allow_nulls": False},
            )
        assert result["failed_rules_count"] > 0
        assert result["issues"]
        assert all("evidence_ref" in issue for issue in result["issues"])
        assert result["affected_columns"]

    @pytest.mark.asyncio
    async def test_tool_4_check_release_policy(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            clean = await call_json(
                session, "check_release_policy", {"dataset_id": seeded.clean_id}
            )
            dirty = await call_json(
                session, "check_release_policy", {"dataset_id": seeded.dirty_id}
            )
        assert clean["is_release_eligible"] is True
        assert dirty["is_release_eligible"] is False
        assert dirty["risk_band"] in {"HIGH", "CRITICAL"}
        assert dirty["blocking_reasons"]
        assert set(dirty["category_scores"]) == {
            "sensitive_information",
            "data_quality",
            "licensing_provenance",
            "metadata_completeness",
            "policy_violations",
        }

    @pytest.mark.asyncio
    async def test_tool_5_generate_risk_report(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            result = await call_json(
                session, "generate_risk_report", {"dataset_id": seeded.dirty_id}
            )
        assert result["dataset_id"] == seeded.dirty_id
        assert result["content_hash"]
        assert result["risk_assessment"]["total_risk_score"] > 0
        assert result["profiling_summary"]["row_count"] == 5
        assert result["privacy_summary"]["total_findings"] > 0
        assert result["total_findings"] > 0

    @pytest.mark.asyncio
    async def test_tool_6_propose_transformation(self, seeded):
        operations = [
            {
                "operation": "mask_column",
                "column": "email_address",
                "strategy": "partial_email",
            },
            {
                "operation": "mask_column",
                "column": "phone_number",
                "strategy": "last_4_visible",
            },
            {"operation": "remove_column", "column": "full_name"},
        ]
        async with mcp_client(make_server(seeded)) as session:
            result = await call_json(
                session,
                "propose_transformation",
                {
                    "dataset_id": seeded.dirty_id,
                    "operations": operations,
                    "rationale": "Mask direct identifiers before release",
                },
            )
        assert result["status"] == "PROPOSED"
        assert result["target_version"] == 2
        assert result["operations_count"] == 3
        assert result["simulated_output_hash"]
        assert "full_name" in result["preview"]["columns_removed"]
        assert "email_address" in result["preview"]["columns_modified"]
        assert result["preview"]["input_row_count"] == 5

    @pytest.mark.asyncio
    async def test_tool_7_prepare_release(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            result = await call_json(
                session,
                "prepare_release",
                {
                    "dataset_id": seeded.clean_id,
                    "destination_target": "s3://release-evidence/exports",
                    "release_notes": "Quarterly aggregate export",
                },
            )
        assert result["status"] == "STAGED"
        assert len(result["artifact_hash"]) == 64
        assert result["release_id"].startswith("rel_")
        assert result["approval_required"] is True
        assert result["is_release_eligible"] is True

    @pytest.mark.asyncio
    async def test_tool_8_submit_for_review(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            prepared = await call_json(
                session,
                "prepare_release",
                {"dataset_id": seeded.clean_id, "destination_target": "s3://release-evidence/exports"},
            )
            result = await call_json(
                session,
                "submit_for_review",
                {
                    "dataset_id": seeded.clean_id,
                    "staged_release_id": prepared["release_id"],
                    "reviewer_notes": "Please verify masking and licensing",
                },
            )
        assert result["release_id"] == prepared["release_id"]
        assert result["status"] == "PENDING_REVIEW"
        assert result["approval_required"] is True
        assert "AI cannot authorize publication" in result["message"]

    @pytest.mark.asyncio
    async def test_tool_9_get_approval_status(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            submitted = await prepare_and_submit(session, seeded.clean_id)
            result = await call_json(
                session, "get_approval_status", {"release_id": submitted["release_id"]}
            )
        assert result["status"] == "PENDING_REVIEW"
        assert result["is_approved"] is False
        assert result["approval"] is None
        assert result["publishable"] is False
        assert "apr_" not in json.dumps(result)

    @pytest.mark.asyncio
    async def test_tool_10_publish_dataset_requires_human_approval(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            submitted = await prepare_and_submit(session, seeded.clean_id)
            release_id = submitted["release_id"]
            artifact_hash = submitted["artifact_hash"]

            # AI-fabricated approval identifier is rejected.
            message = await call_error(
                session,
                "publish_dataset",
                {
                    "release_id": release_id,
                    "approval_id": "apr_" + "a" * 32,
                    "expected_artifact_hash": artifact_hash,
                },
            )
            assert "Human authorization required" in message

            # Trusted human channel records approval outside MCP.
            approval = seeded.service.record_human_approval(
                organization_id=ORG_A,
                release_id=release_id,
                artifact_hash=artifact_hash,
                approver_id="human-steward-1",
            )
            published = await call_json(
                session,
                "publish_dataset",
                {
                    "release_id": release_id,
                    "approval_id": approval.approval_id,
                    "expected_artifact_hash": artifact_hash,
                },
            )
            assert published["status"] == "PUBLISHED"
            assert published["published_artifact_hash"] == artifact_hash
            assert published["approval"]["approver_type"] == "HUMAN"

            # Repeating the same authorized publication is idempotent.
            repeat = await call_json(
                session,
                "publish_dataset",
                {
                    "release_id": release_id,
                    "approval_id": approval.approval_id,
                    "expected_artifact_hash": artifact_hash,
                },
            )
            assert repeat["status"] == "PUBLISHED"

    @pytest.mark.asyncio
    async def test_tool_11_verify_publication(self, seeded):
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
                "publish_dataset",
                {
                    "release_id": submitted["release_id"],
                    "approval_id": approval.approval_id,
                    "expected_artifact_hash": submitted["artifact_hash"],
                },
            )
            result = await call_json(
                session, "verify_publication", {"release_id": submitted["release_id"]}
            )
        assert result["is_published"] is True
        assert result["integrity_verified"] is True
        assert result["verified_artifact_hash"] == submitted["artifact_hash"]

    @pytest.mark.asyncio
    async def test_tool_12_withdraw_release(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            submitted = await prepare_and_submit(session, seeded.clean_id)
            result = await call_json(
                session,
                "withdraw_release",
                {
                    "release_id": submitted["release_id"],
                    "reason": "Audit found an unresolved licensing gap",
                },
            )
        assert result["current_status"] == "WITHDRAWN"
        assert result["prior_status"] == "PENDING_REVIEW"


# =============================================================================
# Resources
# =============================================================================
class TestMCPResources:
    @pytest.mark.asyncio
    async def test_list_resources_and_templates(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            static = await session.list_resources()
            templates = await session.list_resource_templates()

        assert [str(resource.uri) for resource in static.resources] == [
            "releasegate://policies/current",
            "releasegate://system/status",
        ]
        assert [template.uriTemplate for template in templates.resourceTemplates] == [
            "releasegate://datasets/{dataset_id}/profile",
            "releasegate://releases/{release_id}/evidence",
        ]

    @pytest.mark.asyncio
    async def test_policies_current(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            policy = await read_resource(session, "releasegate://policies/current")
        assert policy["policy_version"] == "1.0.0"
        assert policy["weight_allocations"] == {
            "sensitive_information": 35.0,
            "data_quality": 20.0,
            "licensing_provenance": 20.0,
            "metadata_completeness": 10.0,
            "policy_violations": 15.0,
            "total": 100.0,
        }
        assert policy["human_authorization"]["ai_may_authorize_publication"] is False

    @pytest.mark.asyncio
    async def test_dataset_profile(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            profile = await read_resource(
                session, f"releasegate://datasets/{seeded.clean_id}/profile"
            )
        assert profile["dataset_id"] == seeded.clean_id
        assert profile["profile"]["row_count"] == 3
        assert profile["profile"]["columns"] == ["record_id", "region_code", "amount"]
        assert profile["content_hash"]

    @pytest.mark.asyncio
    async def test_release_evidence(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            prepared = await call_json(
                session,
                "prepare_release",
                {"dataset_id": seeded.clean_id, "destination_target": "s3://release-evidence/exports"},
            )
            evidence = await read_resource(
                session, f"releasegate://releases/{prepared['release_id']}/evidence"
            )
        assert evidence["release_id"] == prepared["release_id"]
        assert evidence["status"] == "STAGED"
        assert evidence["artifact_hash"] == prepared["artifact_hash"]
        assert evidence["risk_assessment"]["risk_score"] == prepared["risk_score"]
        assert evidence["approval_records"] == []

    @pytest.mark.asyncio
    async def test_system_status(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            status = await read_resource(session, "releasegate://system/status")
        assert status["status"] == "HEALTHY"
        assert status["mcp_server"] == {
            "database_access": "NONE",
            "filesystem_access": "SERVICE_LAYER_ONLY",
            "arbitrary_code_execution": "PROHIBITED",
            "publication_authorization": "HUMAN_ONLY",
            "identity_source": "SERVER_SESSION",
        }
        assert status["planes"]["local_worker_plane"]["raw_data_boundary"] == "LOCAL_ONLY"

    @pytest.mark.asyncio
    async def test_unknown_resource_is_rejected(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            with pytest.raises(McpError):
                await session.read_resource("releasegate://datasets/not-a-uuid/profile")


# =============================================================================
# Prompts
# =============================================================================
class TestMCPPrompts:
    @pytest.mark.asyncio
    async def test_four_frozen_prompts_are_exposed(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            listed = await session.list_prompts()
        assert names(listed.prompts) == [
            "triage_dataset",
            "investigate_findings",
            "propose_remediation",
            "challenger_review",
        ]
        for prompt in listed.prompts:
            assert prompt.description
            assert prompt.arguments

    @pytest.mark.asyncio
    async def test_triage_prompt(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            prompt = await session.get_prompt(
                "triage_dataset", {"dataset_id": seeded.clean_id, "version_number": "2"}
            )
        text = prompt.messages[0].content.text
        assert "ReleaseGate Data Governance Triage Agent" in text
        assert seeded.clean_id in text
        assert "version 2" in text
        assert "inspect_dataset" in text
        assert "Do not request, infer, or display raw dataset values" in text

    @pytest.mark.asyncio
    async def test_investigate_prompt(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            prompt = await session.get_prompt(
                "investigate_findings", {"dataset_id": seeded.dirty_id}
            )
        text = prompt.messages[0].content.text
        assert "Privacy and Quality Investigation Agent" in text
        assert "detect_sensitive_data" in text
        assert "validate_data_quality" in text
        assert "Never ask for raw rows" in text

    @pytest.mark.asyncio
    async def test_remediation_prompt(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            prompt = await session.get_prompt(
                "propose_remediation", {"dataset_id": seeded.dirty_id}
            )
        text = prompt.messages[0].content.text
        assert "Safe Transformation Architect" in text
        assert "Allowlisted operations only" in text
        assert "No SQL, shell, executable code" in text
        assert "propose_transformation" in text

    @pytest.mark.asyncio
    async def test_challenger_prompt(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            prompt = await session.get_prompt(
                "challenger_review", {"release_id": "rel_0123456789ab"}
            )
        text = prompt.messages[0].content.text
        assert "Independent Challenger AI Reviewer" in text
        assert "AI cannot authorize publication" in text
        assert "releasegate://releases/rel_0123456789ab/evidence" in text

    @pytest.mark.asyncio
    async def test_invalid_prompt_arguments_are_rejected(self, seeded):
        async with mcp_client(make_server(seeded)) as session:
            with pytest.raises(McpError):
                await session.get_prompt("triage_dataset", {"dataset_id": "ds-1234"})
            with pytest.raises(McpError):
                await session.get_prompt("challenger_review", {"release_id": "rel_123"})
            with pytest.raises(McpError):
                await session.get_prompt("triage_dataset", {})


# =============================================================================
# Zero raw-value leakage
# =============================================================================
class TestZeroRawValueLeakage:
    @pytest.mark.asyncio
    async def test_tools_resources_and_audit_never_return_raw_values(self, seeded, tmp_path):
        audit_logger.clear()
        texts = []

        async with mcp_client(make_server(seeded)) as session:
            dirty_calls = [
                ("inspect_dataset", {"dataset_id": seeded.dirty_id}),
                (
                    "detect_sensitive_data",
                    {"dataset_id": seeded.dirty_id, "confidence_threshold": 0.4},
                ),
                (
                    "validate_data_quality",
                    {"dataset_id": seeded.dirty_id, "allow_nulls": False},
                ),
                ("check_release_policy", {"dataset_id": seeded.dirty_id}),
                ("generate_risk_report", {"dataset_id": seeded.dirty_id}),
                (
                    "propose_transformation",
                    {
                        "dataset_id": seeded.dirty_id,
                        "operations": [
                            {
                                "operation": "pseudonymize_column",
                                "column": "email_address",
                            }
                        ],
                        "rationale": "Tokenize identifiers for analytics release",
                    },
                ),
            ]
            for name, arguments in dirty_calls:
                result = await call_tool(session, name, arguments)
                assert not result.isError, f"{name}: {result.content[0].text}"
                texts.append(result.content[0].text)

            for uri in (
                "releasegate://policies/current",
                "releasegate://system/status",
                f"releasegate://datasets/{seeded.dirty_id}/profile",
            ):
                texts.append((await session.read_resource(uri)).contents[0].text)

            for prompt_name, arguments in (
                ("triage_dataset", {"dataset_id": seeded.dirty_id}),
                ("investigate_findings", {"dataset_id": seeded.dirty_id}),
                ("propose_remediation", {"dataset_id": seeded.dirty_id}),
            ):
                prompt = await session.get_prompt(prompt_name, arguments)
                texts.append(prompt.messages[0].content.text)

        combined = "\n".join(texts)
        for raw_value in RAW_VALUES:
            assert raw_value not in combined, f"Raw value leaked: {raw_value}"
        # Raw CSV rows must never appear either.
        assert "Alice Smith,alice@example.com" not in combined
        assert "invalid-date" not in combined

        records = audit_logger.get_recent_records(limit=50)
        assert records
        audit_text = json.dumps(records)
        for raw_value in RAW_VALUES:
            assert raw_value not in audit_text, f"Raw value leaked into audit: {raw_value}"
        assert all(record["organization_id"] == ORG_A for record in records)
        assert all(record["principal_id"] for record in records)
        assert str(tmp_path) not in audit_text
