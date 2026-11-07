"""
Comprehensive Integration Test Suite for ReleaseGate Model Context Protocol (MCP) Server.
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.

Verifies:
1. Strict Pydantic argument validation across all 12 MCP tool schemas (valid & invalid rejection).
2. MCP Tool Execution across the entire dataset lifecycle (inspect, detect, quality, policy, transform, stage, submit, approve, publish, verify, withdraw).
3. Role-Based Access Control (RBAC) permissions (ADMIN, STEWARD, AUDITOR, USER).
4. Human Approval Constraint on publish_dataset (AI cannot authorize publication; hash-bound token mandatory).
5. All 4 frozen MCP resources (policies, profile, evidence, system status).
6. All 4 frozen MCP prompts (triage, investigate, remediation, challenger review).
7. Strict Zero Raw Value Leakage Invariant across all responses and audit records.
"""

import json
import uuid
import pytest
from pydantic import ValidationError

from mcp_server.schemas.tools import (
    CheckReleasePolicyArgs,
    DetectSensitiveDataArgs,
    GenerateRiskReportArgs,
    GetApprovalStatusArgs,
    InspectDatasetArgs,
    PrepareReleaseArgs,
    ProposeTransformationArgs,
    PublishDatasetArgs,
    SubmitForReviewArgs,
    TransformationOperationSpec,
    ValidateDataQualityArgs,
    VerifyPublicationArgs,
    WithdrawReleaseArgs,
)
from mcp_server.security.audit import audit_logger
from mcp_server.security.permissions import (
    HumanApprovalRequiredError,
    MCPPermissionError,
    ToolRole,
    verify_human_approval_token,
    verify_tool_permission,
)
from mcp_server.server import create_mcp_server
from mcp_server.service_interface import ReleaseGateService, ServiceNotFoundError, ServiceValidationError


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def mock_dataset_content() -> bytes:
    """Sample dataset containing PII and quality issues."""
    csv_text = (
        "id,full_name,email_address,phone_number,income,registration_date\n"
        "1,Alice Smith,alice@example.com,555-010-1234,75000,2023-01-15\n"
        "2,Bob Jones,bob@workplace.org,555-010-5678,82000,2023-02-20\n"
        "3,Charlie Brown,charlie@test.net,555-010-9012,,2023-03-25\n"
        "4,Diana Prince,diana@themyscira.gov,555-010-3456,120000,invalid-date\n"
        "5,Evan Wright,evan@corp.com,555-010-7890,65000,2023-05-10\n"
    )
    return csv_text.encode("utf-8")


@pytest.fixture
def service_with_dataset(mock_dataset_content: bytes) -> ReleaseGateService:
    """Service instance pre-seeded with a sample dataset."""
    srv = ReleaseGateService()
    dataset_id = str(uuid.uuid4())
    srv.register_dataset_artifact(
        dataset_id=dataset_id,
        version_number=1,
        content=mock_dataset_content,
        file_format="csv",
        name="Customer Analytics Dataset",
        description="Tabular user records for release governance testing",
    )
    srv.default_test_dataset_id = dataset_id
    return srv


@pytest.fixture
def mcp_server_instance(service_with_dataset: ReleaseGateService):
    """FastMCP server bound to the pre-seeded service."""
    return create_mcp_server(service=service_with_dataset)


# =============================================================================
# PART 1: Strict Pydantic Schema Validation Tests (All 12 Tools)
# =============================================================================
class TestMCPToolSchemas:
    """Verifies strict input validation and prohibition of extra/malformed parameters."""

    def test_schema_inspect_dataset_valid_and_invalid(self):
        # Valid
        valid = InspectDatasetArgs(dataset_id="ds-100", version_number=2)
        assert valid.dataset_id == "ds-100"
        assert valid.version_number == 2

        # Invalid blank ID
        with pytest.raises(ValidationError):
            InspectDatasetArgs(dataset_id="   ")

        # Invalid version number < 1
        with pytest.raises(ValidationError):
            InspectDatasetArgs(dataset_id="ds-100", version_number=0)

        # Prohibited extra parameter injection (extra="forbid")
        with pytest.raises(ValidationError):
            InspectDatasetArgs(dataset_id="ds-100", malicious_payload="drop table")

    def test_schema_detect_sensitive_data_valid_and_invalid(self):
        # Valid
        valid = DetectSensitiveDataArgs(
            dataset_id="ds-100",
            confidence_threshold=0.75,
            entities=["PERSON", "EMAIL_ADDRESS"],
        )
        assert valid.confidence_threshold == 0.75

        # Invalid confidence bounds (< 0.0 or > 1.0)
        with pytest.raises(ValidationError):
            DetectSensitiveDataArgs(dataset_id="ds-100", confidence_threshold=1.5)
        with pytest.raises(ValidationError):
            DetectSensitiveDataArgs(dataset_id="ds-100", confidence_threshold=-0.1)

    def test_schema_validate_data_quality_valid_and_invalid(self):
        valid = ValidateDataQualityArgs(
            dataset_id="ds-100",
            allow_nulls=False,
            allow_duplicates=False,
        )
        assert valid.allow_nulls is False

        with pytest.raises(ValidationError):
            ValidateDataQualityArgs(dataset_id="ds-100", injected_field="bad")

    def test_schema_check_release_policy_valid_and_invalid(self):
        valid = CheckReleasePolicyArgs(
            dataset_id="ds-100",
            policy_version="1.0.0",
            domain="internal_analytics",
        )
        assert valid.policy_version == "1.0.0"

        with pytest.raises(ValidationError):
            CheckReleasePolicyArgs(dataset_id="ds-100", unknown_key="invalid")

    def test_schema_generate_risk_report_valid_and_invalid(self):
        valid = GenerateRiskReportArgs(dataset_id="ds-100", version_number=1)
        assert valid.version_number == 1

        with pytest.raises(ValidationError):
            GenerateRiskReportArgs(dataset_id="ds-100", version_number=-5)

    def test_schema_propose_transformation_valid_and_invalid(self):
        # Valid
        op = TransformationOperationSpec(
            operation="mask_column",
            column="email_address",
            parameters={"strategy": "partial_email"},
        )
        valid = ProposeTransformationArgs(
            dataset_id="ds-100",
            operations=[op],
            rationale="Redacting email addresses for GDPR compliance",
        )
        assert len(valid.operations) == 1

        # Prohibited operation rejection
        with pytest.raises(ValidationError) as exc_info:
            TransformationOperationSpec(
                operation="execute_arbitrary_python",
                column="email",
            )
        assert "is prohibited" in str(exc_info.value)

        # Empty operations list rejection
        with pytest.raises(ValidationError):
            ProposeTransformationArgs(
                dataset_id="ds-100",
                operations=[],
                rationale="Empty ops",
            )

    def test_schema_prepare_release_valid_and_invalid(self):
        # Valid
        valid = PrepareReleaseArgs(
            dataset_id="ds-100",
            source_version_number=1,
            destination_target="s3://analytics-export",
        )
        assert valid.destination_target.startswith("s3://")

        # Invalid destination target URI protocol
        with pytest.raises(ValidationError) as exc_info:
            PrepareReleaseArgs(
                dataset_id="ds-100",
                destination_target="file:///etc/passwd",
            )
        assert "destination_target must use an approved URI protocol" in str(exc_info.value)

    def test_schema_submit_for_review_valid_and_invalid(self):
        valid = SubmitForReviewArgs(
            dataset_id="ds-100",
            version_number=1,
            reviewer_notes="Ready for challenger audit",
        )
        assert valid.reviewer_notes == "Ready for challenger audit"

        with pytest.raises(ValidationError):
            SubmitForReviewArgs(dataset_id="ds-100", invalid_opt="xyz")

    def test_schema_get_approval_status_valid_and_invalid(self):
        valid = GetApprovalStatusArgs(release_id="rel_12345")
        assert valid.release_id == "rel_12345"

        with pytest.raises(ValidationError):
            GetApprovalStatusArgs(release_id="rel_12345", rogue="param")

    def test_schema_publish_dataset_valid_and_invalid(self):
        # Valid
        valid = PublishDatasetArgs(
            release_id="rel_12345",
            approval_token="human-token-rel12345-abcdef0123456789",
            expected_artifact_hash="a" * 64,
        )
        assert len(valid.expected_artifact_hash) == 64

        # Token too short (< 16 chars)
        with pytest.raises(ValidationError):
            PublishDatasetArgs(
                release_id="rel_12345",
                approval_token="short",
                expected_artifact_hash="a" * 64,
            )

        # Non-hex or invalid length sha256 hash
        with pytest.raises(ValidationError):
            PublishDatasetArgs(
                release_id="rel_12345",
                approval_token="human-token-rel12345-abcdef0123456789",
                expected_artifact_hash="not_a_valid_sha256",
            )

    def test_schema_verify_publication_valid_and_invalid(self):
        valid = VerifyPublicationArgs(release_id="rel_12345")
        assert valid.release_id == "rel_12345"

        with pytest.raises(ValidationError):
            VerifyPublicationArgs(release_id="rel_12345", unexpected=True)

    def test_schema_withdraw_release_valid_and_invalid(self):
        valid = WithdrawReleaseArgs(
            release_id="rel_12345",
            reason="Detected anomalous duplicate values after export",
        )
        assert valid.reason.startswith("Detected")

        # Too short reason
        with pytest.raises(ValidationError):
            WithdrawReleaseArgs(release_id="rel_12345", reason="no")


# =============================================================================
# PART 2: RBAC Permissions Tests
# =============================================================================
class TestMCPPermissions:
    """Verifies Role-Based Access Control allowlists and enforcement."""

    def test_user_role_permissions(self):
        # USER can run inspection and transformations
        verify_tool_permission("inspect_dataset", "USER")
        verify_tool_permission("detect_sensitive_data", "USER")
        verify_tool_permission("validate_data_quality", "USER")
        verify_tool_permission("check_release_policy", "USER")
        verify_tool_permission("propose_transformation", "USER")
        verify_tool_permission("prepare_release", "USER")
        verify_tool_permission("submit_for_review", "USER")

        # USER cannot publish or withdraw
        with pytest.raises(MCPPermissionError) as exc_info:
            verify_tool_permission("publish_dataset", "USER")
        assert "Permission denied: Role 'USER' is not authorized to execute tool 'publish_dataset'" in str(exc_info.value)

        with pytest.raises(MCPPermissionError):
            verify_tool_permission("withdraw_release", "USER")

    def test_auditor_role_permissions(self):
        # AUDITOR has read-only audit inspection access
        verify_tool_permission("inspect_dataset", "AUDITOR")
        verify_tool_permission("detect_sensitive_data", "AUDITOR")
        verify_tool_permission("validate_data_quality", "AUDITOR")
        verify_tool_permission("check_release_policy", "AUDITOR")
        verify_tool_permission("generate_risk_report", "AUDITOR")
        verify_tool_permission("get_approval_status", "AUDITOR")
        verify_tool_permission("verify_publication", "AUDITOR")

        # AUDITOR cannot modify datasets, propose transforms, publish, or withdraw
        with pytest.raises(MCPPermissionError):
            verify_tool_permission("propose_transformation", "AUDITOR")
        with pytest.raises(MCPPermissionError):
            verify_tool_permission("prepare_release", "AUDITOR")
        with pytest.raises(MCPPermissionError):
            verify_tool_permission("publish_dataset", "AUDITOR")
        with pytest.raises(MCPPermissionError):
            verify_tool_permission("withdraw_release", "AUDITOR")

    def test_steward_and_admin_role_permissions(self):
        # STEWARD has governance authority over all lifecycle tools
        for tool in [
            "inspect_dataset", "detect_sensitive_data", "validate_data_quality",
            "check_release_policy", "generate_risk_report", "propose_transformation",
            "prepare_release", "submit_for_review", "get_approval_status",
            "publish_dataset", "verify_publication", "withdraw_release",
        ]:
            verify_tool_permission(tool, "STEWARD")
            verify_tool_permission(tool, "ADMIN")

    def test_invalid_role_rejection(self):
        with pytest.raises(MCPPermissionError) as exc_info:
            verify_tool_permission("inspect_dataset", "ANONYMOUS_HACKER")
        assert "Invalid or unrecognized caller role" in str(exc_info.value)


# =============================================================================
# PART 3: MCP Tool End-to-End Execution Tests
# =============================================================================
class TestMCPToolExecution:
    """Verifies execution of all 12 MCP tools through FastMCP interface."""

    @pytest.mark.asyncio
    async def test_tool_1_inspect_dataset(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        raw_res = await mcp_server_instance.call_tool(
            "inspect_dataset",
            {"dataset_id": ds_id, "version_number": 1, "caller_role": "STEWARD"},
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["dataset_id"] == ds_id
        assert content_json["version_number"] == 1
        assert "risk_score" in content_json
        assert "risk_band" in content_json
        assert "summary_report" in content_json
        assert "findings" in content_json
        assert content_json["findings_count"] > 0

    @pytest.mark.asyncio
    async def test_tool_2_detect_sensitive_data(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        raw_res = await mcp_server_instance.call_tool(
            "detect_sensitive_data",
            {"dataset_id": ds_id, "version_number": 1, "confidence_threshold": 0.5},
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["dataset_id"] == ds_id
        assert content_json["total_findings"] > 0
        detected = content_json["detected_entities"]
        assert any(e in detected for e in ["EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON"])
        # Ensure coordinates are present
        for f in content_json["findings"]:
            assert "evidence_ref" in f
            assert "column_name" in f

    @pytest.mark.asyncio
    async def test_tool_3_validate_data_quality(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        raw_res = await mcp_server_instance.call_tool(
            "validate_data_quality",
            {"dataset_id": ds_id, "version_number": 1, "allow_nulls": False},
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["dataset_id"] == ds_id
        assert "quality_score" in content_json
        assert "issues" in content_json
        assert content_json["failed_rules_count"] > 0

    @pytest.mark.asyncio
    async def test_tool_4_check_release_policy(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        raw_res = await mcp_server_instance.call_tool(
            "check_release_policy",
            {"dataset_id": ds_id, "version_number": 1, "policy_version": "1.0.0"},
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["dataset_id"] == ds_id
        assert "is_release_eligible" in content_json
        assert "risk_score" in content_json
        assert "risk_band" in content_json
        assert "category_scores" in content_json

    @pytest.mark.asyncio
    async def test_tool_5_generate_risk_report(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        raw_res = await mcp_server_instance.call_tool(
            "generate_risk_report",
            {"dataset_id": ds_id, "version_number": 1},
        )
        content_json = json.loads(raw_res[0][0].text)

        assert "report_id" in content_json
        assert content_json["dataset_id"] == ds_id
        assert "risk_assessment" in content_json
        assert "profiling_summary" in content_json

    @pytest.mark.asyncio
    async def test_tool_6_propose_transformation(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        operations = [
            {
                "operation": "mask_column",
                "column": "email_address",
                "parameters": {"strategy": "partial_email"},
            },
            {
                "operation": "mask_column",
                "column": "phone_number",
                "parameters": {"strategy": "last_4_digits"},
            },
            {
                "operation": "remove_column",
                "column": "full_name",
            },
        ]
        raw_res = await mcp_server_instance.call_tool(
            "propose_transformation",
            {
                "dataset_id": ds_id,
                "version_number": 1,
                "operations": operations,
                "rationale": "Masking direct identifiers to pass privacy release threshold",
            },
        )
        content_json = json.loads(raw_res[0][0].text)

        assert "proposal_id" in content_json
        assert content_json["status"] == "PROPOSED"
        assert content_json["target_version"] == 2
        assert "simulated_output_hash" in content_json
        assert "preview" in content_json
        preview = content_json["preview"]
        assert "full_name" in preview["columns_removed"]
        assert "email_address" in preview["columns_modified"]

    @pytest.mark.asyncio
    async def test_tool_7_prepare_release(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        raw_res = await mcp_server_instance.call_tool(
            "prepare_release",
            {
                "dataset_id": ds_id,
                "source_version_number": 1,
                "destination_target": "s3://analytics-export",
                "release_notes": "Staged release package for Q4 analytics export",
            },
        )
        content_json = json.loads(raw_res[0][0].text)

        assert "release_id" in content_json
        assert content_json["status"] == "STAGED"
        assert len(content_json["artifact_hash"]) == 64

    @pytest.mark.asyncio
    async def test_tool_8_submit_for_review(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        prep_res = await mcp_server_instance.call_tool(
            "prepare_release",
            {"dataset_id": ds_id, "source_version_number": 1},
        )
        release_id = json.loads(prep_res[0][0].text)["release_id"]

        raw_res = await mcp_server_instance.call_tool(
            "submit_for_review",
            {
                "dataset_id": ds_id,
                "version_number": 1,
                "staged_release_id": release_id,
                "reviewer_notes": "Please verify PII masking before steward sign-off",
            },
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["release_id"] == release_id
        assert content_json["status"] == "PENDING_REVIEW"

    @pytest.mark.asyncio
    async def test_tool_9_get_approval_status(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        prep_res = await mcp_server_instance.call_tool(
            "prepare_release",
            {"dataset_id": ds_id, "source_version_number": 1},
        )
        release_id = json.loads(prep_res[0][0].text)["release_id"]

        raw_res = await mcp_server_instance.call_tool(
            "get_approval_status",
            {"release_id": release_id},
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["release_id"] == release_id
        assert content_json["status"] == "STAGED"
        assert content_json["is_approved"] is False

    @pytest.mark.asyncio
    async def test_tool_10_publish_dataset_enforces_human_token(self, mcp_server_instance, service_with_dataset):
        """
        CRITICAL ARCHITECTURE REQUIREMENT:
        AI models cannot authorize publication.
        Fake or arbitrary tokens must be strictly rejected with HumanApprovalRequiredError.
        Authentic tokens bound to the artifact hash succeed.
        """
        ds_id = service_with_dataset.default_test_dataset_id
        prep_res = await mcp_server_instance.call_tool(
            "prepare_release",
            {"dataset_id": ds_id, "source_version_number": 1},
        )
        rel_info = json.loads(prep_res[0][0].text)
        release_id = rel_info["release_id"]
        artifact_hash = rel_info["artifact_hash"]

        # 1. Attempt AI publication with counterfeit token -> BLOCKED
        with pytest.raises(Exception) as exc_info:
            await mcp_server_instance.call_tool(
                "publish_dataset",
                {
                    "release_id": release_id,
                    "approval_token": "ai-generated-token-attempting-publication-bypass",
                    "expected_artifact_hash": artifact_hash,
                },
            )
        assert "Human approval verification failed" in str(exc_info.value)

        # 2. Attempt publication with mismatched hash -> BLOCKED
        with pytest.raises(Exception) as exc_info:
            await mcp_server_instance.call_tool(
                "publish_dataset",
                {
                    "release_id": release_id,
                    "approval_token": f"human-token-{release_id[:8]}-{artifact_hash[:16]}",
                    "expected_artifact_hash": "f" * 64,
                },
            )
        assert "Artifact hash mismatch" in str(exc_info.value)

        # 3. Supply authentic Human Steward approval token -> SUCCESS
        valid_human_token = f"human-token-{release_id[:8]}-{artifact_hash[:16]}"
        pub_res = await mcp_server_instance.call_tool(
            "publish_dataset",
            {
                "release_id": release_id,
                "approval_token": valid_human_token,
                "expected_artifact_hash": artifact_hash,
            },
        )
        content_json = json.loads(pub_res[0][0].text)

        assert content_json["status"] == "PUBLISHED"
        assert content_json["published_artifact_hash"] == artifact_hash

    @pytest.mark.asyncio
    async def test_tool_11_verify_publication(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        prep_res = await mcp_server_instance.call_tool(
            "prepare_release",
            {"dataset_id": ds_id, "source_version_number": 1},
        )
        rel_info = json.loads(prep_res[0][0].text)
        release_id = rel_info["release_id"]
        artifact_hash = rel_info["artifact_hash"]

        # Publish first with valid human token
        valid_human_token = f"human-token-{release_id[:8]}-{artifact_hash[:16]}"
        await mcp_server_instance.call_tool(
            "publish_dataset",
            {
                "release_id": release_id,
                "approval_token": valid_human_token,
                "expected_artifact_hash": artifact_hash,
            },
        )

        # Verify publication
        raw_res = await mcp_server_instance.call_tool(
            "verify_publication",
            {"release_id": release_id},
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["release_id"] == release_id
        assert content_json["is_published"] is True
        assert content_json["integrity_verified"] is True
        assert content_json["verified_artifact_hash"] == artifact_hash

    @pytest.mark.asyncio
    async def test_tool_12_withdraw_release(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        prep_res = await mcp_server_instance.call_tool(
            "prepare_release",
            {"dataset_id": ds_id, "source_version_number": 1},
        )
        release_id = json.loads(prep_res[0][0].text)["release_id"]

        raw_res = await mcp_server_instance.call_tool(
            "withdraw_release",
            {
                "release_id": release_id,
                "reason": "Data steward identified unapproved third-party attributes",
            },
        )
        content_json = json.loads(raw_res[0][0].text)

        assert content_json["release_id"] == release_id
        assert content_json["current_status"] == "WITHDRAWN"


# =============================================================================
# PART 4: MCP Resources Tests (All 4 Resources)
# =============================================================================
class TestMCPResources:
    """Verifies reading all 4 frozen MCP resources."""

    @pytest.mark.asyncio
    async def test_resource_policies_current(self, mcp_server_instance):
        res = await mcp_server_instance.read_resource("releasegate://policies/current")
        assert len(res) > 0
        policy_data = json.loads(res[0].content)

        assert policy_data["policy_version"] == "1.0.0"
        assert "risk_bands" in policy_data
        assert "weight_allocations" in policy_data
        assert policy_data["weight_allocations"]["sensitive_information"] == 35
        assert policy_data["weight_allocations"]["data_quality"] == 20
        assert policy_data["weight_allocations"]["licensing_provenance"] == 20
        assert policy_data["weight_allocations"]["metadata_completeness"] == 10
        assert policy_data["weight_allocations"]["policy_violations"] == 15

    @pytest.mark.asyncio
    async def test_resource_dataset_profile(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        res = await mcp_server_instance.read_resource(f"releasegate://datasets/{ds_id}/profile")
        assert len(res) > 0
        profile_data = json.loads(res[0].content)

        assert profile_data["dataset_id"] == ds_id
        assert "profile" in profile_data
        assert profile_data["profile"]["row_count"] == 5
        assert "email_address" in profile_data["profile"]["columns"]

    @pytest.mark.asyncio
    async def test_resource_release_evidence(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        prep_res = await mcp_server_instance.call_tool(
            "prepare_release",
            {"dataset_id": ds_id, "source_version_number": 1},
        )
        release_id = json.loads(prep_res[0][0].text)["release_id"]

        res = await mcp_server_instance.read_resource(f"releasegate://releases/{release_id}/evidence")
        assert len(res) > 0
        evidence_data = json.loads(res[0].content)

        assert evidence_data["release_id"] == release_id
        assert evidence_data["status"] == "STAGED"
        assert len(evidence_data["artifact_hash"]) == 64

    @pytest.mark.asyncio
    async def test_resource_system_status(self, mcp_server_instance):
        res = await mcp_server_instance.read_resource("releasegate://system/status")
        assert len(res) > 0
        status_data = json.loads(res[0].content)

        assert status_data["status"] == "HEALTHY"
        assert status_data["planes"]["local_worker_plane"]["isolation_enforced"] is True
        assert status_data["planes"]["cloud_control_plane"]["metadata_only"] is True


# =============================================================================
# PART 5: MCP Prompts Tests (All 4 Prompts)
# =============================================================================
class TestMCPPrompts:
    """Verifies retrieval of all 4 frozen MCP prompt templates."""

    @pytest.mark.asyncio
    async def test_prompt_triage_dataset(self, mcp_server_instance):
        prompt = await mcp_server_instance.get_prompt("triage_dataset", {"dataset_id": "ds-1234"})
        text = prompt.messages[0].content.text
        assert "ReleaseGate Data Governance Triage Agent" in text
        assert "ds-1234" in text
        assert "inspect_dataset" in text

    @pytest.mark.asyncio
    async def test_prompt_investigate_findings(self, mcp_server_instance):
        prompt = await mcp_server_instance.get_prompt("investigate_findings", {"dataset_id": "ds-1234"})
        text = prompt.messages[0].content.text
        assert "Privacy and Quality Investigation Agent" in text
        assert "detect_sensitive_data" in text
        assert "validate_data_quality" in text

    @pytest.mark.asyncio
    async def test_prompt_propose_remediation(self, mcp_server_instance):
        prompt = await mcp_server_instance.get_prompt("propose_remediation", {"dataset_id": "ds-1234"})
        text = prompt.messages[0].content.text
        assert "Safe Transformation Architect" in text
        assert "ALLOWLISTED operations" in text
        assert "propose_transformation" in text

    @pytest.mark.asyncio
    async def test_prompt_challenger_review(self, mcp_server_instance):
        prompt = await mcp_server_instance.get_prompt("challenger_review", {"release_id": "rel-5678"})
        text = prompt.messages[0].content.text
        assert "Independent Challenger AI Reviewer" in text
        assert "rel-5678" in text
        assert "releasegate://releases/rel-5678/evidence" in text
        assert "AI cannot authorize publication" in text


# =============================================================================
# PART 6: Zero Raw Value Leakage Invariant
# =============================================================================
class TestZeroRawValueLeakage:
    """
    Guarantees that raw dataset values (e.g. actual email address strings,
    phone numbers, names) NEVER appear in MCP tool outputs or audit logs.
    """

    @pytest.mark.asyncio
    async def test_no_raw_values_in_inspection_or_audit(self, mcp_server_instance, service_with_dataset):
        ds_id = service_with_dataset.default_test_dataset_id
        res = await mcp_server_instance.call_tool(
            "inspect_dataset",
            {"dataset_id": ds_id, "version_number": 1},
        )
        response_text = res[0][0].text

        # Raw values present in the fixture CSV
        raw_values = [
            "alice@example.com",
            "bob@workplace.org",
            "555-010-1234",
            "555-010-5678",
            "Alice Smith",
            "Diana Prince",
        ]
        for val in raw_values:
            assert val not in response_text, f"LEAKAGE DETECTED: Raw value '{val}' leaked into inspection output!"

        # Verify audit records also contain zero raw values
        for record in audit_logger.get_recent_records(limit=20):
            record_str = json.dumps(record)
            for val in raw_values:
                assert val not in record_str, f"LEAKAGE DETECTED in audit log: '{val}' found!"
