"""
ReleaseGate Model Context Protocol (MCP) Server.
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.

Provides:
- 12 frozen MCP governance tools with strict Pydantic argument schemas and RBAC.
- 4 frozen MCP resources exposing policy, profiles, evidence, and status.
- 4 frozen MCP prompts guiding LLM triage, investigation, remediation, and challenger review.
- Strict isolation: MCP tools never access raw files or databases directly.
- Strict human authorization constraint: AI cannot authorize publication.
"""

from typing import Any, Dict, List, Optional
import json

from mcp.server.fastmcp import FastMCP

from mcp_server.prompts.definitions import (
    render_challenger_review_prompt,
    render_investigate_findings_prompt,
    render_propose_remediation_prompt,
    render_triage_dataset_prompt,
)
from mcp_server.resources.handlers import (
    read_dataset_profile,
    read_policies_current,
    read_release_evidence,
    read_system_status,
)
from mcp_server.service_interface import ReleaseGateService, default_service
from mcp_server.tools.governance_tools import (
    get_approval_status_handler,
    submit_for_review_handler,
    withdraw_release_handler,
)
from mcp_server.tools.inspection_tools import (
    check_release_policy_handler,
    detect_sensitive_data_handler,
    generate_risk_report_handler,
    inspect_dataset_handler,
    validate_data_quality_handler,
)
from mcp_server.tools.publication_tools import (
    publish_dataset_handler,
    verify_publication_handler,
)
from mcp_server.tools.transformation_tools import (
    prepare_release_handler,
    propose_transformation_handler,
)


def create_mcp_server(
    service: Optional[ReleaseGateService] = None,
    server_name: str = "ReleaseGate-Governance-Server",
) -> FastMCP:
    """
    Factory function to construct and configure the official FastMCP server.
    Registers all 12 frozen tools, 4 resources, and 4 prompts.
    """
    srv = service or default_service
    server = FastMCP(
        server_name,
        dependencies=["pydantic", "pandas", "presidio-analyzer"],
    )

    # =========================================================================
    # TOOL 1: inspect_dataset
    # =========================================================================
    @server.tool(
        name="inspect_dataset",
        description="Execute complete local dataset inspection (profiling, PII detection, quality, 100-point policy scoring). Zero raw values returned.",
    )
    def inspect_dataset(
        dataset_id: str,
        version_number: int = 1,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Inspect a dataset and return sanitized audit report and risk score."""
        result = inspect_dataset_handler(
            dataset_id=dataset_id,
            version_number=version_number,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 2: detect_sensitive_data
    # =========================================================================
    @server.tool(
        name="detect_sensitive_data",
        description="Scan dataset for PII entities using Microsoft Presidio Analyzer. Returns sanitized coordinates and confidence scores.",
    )
    def detect_sensitive_data(
        dataset_id: str,
        version_number: int = 1,
        confidence_threshold: float = 0.6,
        entities: Optional[List[str]] = None,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Scan dataset for sensitive information and return sanitized findings."""
        result = detect_sensitive_data_handler(
            dataset_id=dataset_id,
            version_number=version_number,
            confidence_threshold=confidence_threshold,
            entities=entities,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 3: validate_data_quality
    # =========================================================================
    @server.tool(
        name="validate_data_quality",
        description="Evaluate dataset quality rules locally and deterministically. Returns aggregate issue counts without row values.",
    )
    def validate_data_quality(
        dataset_id: str,
        version_number: int = 1,
        allow_nulls: Optional[bool] = None,
        allow_duplicates: Optional[bool] = None,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Validate data quality rules deterministically."""
        result = validate_data_quality_handler(
            dataset_id=dataset_id,
            version_number=version_number,
            allow_nulls=allow_nulls,
            allow_duplicates=allow_duplicates,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 4: check_release_policy
    # =========================================================================
    @server.tool(
        name="check_release_policy",
        description="Evaluate dataset eligibility against 100-point release policy and risk bands.",
    )
    def check_release_policy(
        dataset_id: str,
        version_number: int = 1,
        policy_version: str = "1.0.0",
        domain: Optional[str] = None,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Evaluate dataset against release policy rules."""
        result = check_release_policy_handler(
            dataset_id=dataset_id,
            version_number=version_number,
            policy_version=policy_version,
            domain=domain,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 5: generate_risk_report
    # =========================================================================
    @server.tool(
        name="generate_risk_report",
        description="Generate comprehensive structured risk assessment report with 100-point breakdown.",
    )
    def generate_risk_report(
        dataset_id: str,
        version_number: int = 1,
        policy_version: str = "1.0.0",
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Generate structured risk report."""
        result = generate_risk_report_handler(
            dataset_id=dataset_id,
            version_number=version_number,
            policy_version=policy_version,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 6: propose_transformation
    # =========================================================================
    @server.tool(
        name="propose_transformation",
        description="Validate and simulate allowlisted transformations (masking, pseudonymization, generalization). Original data remains immutable.",
    )
    def propose_transformation(
        dataset_id: str,
        operations: List[Dict[str, Any]],
        rationale: str,
        version_number: int = 1,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Simulate and propose safe transformations."""
        result = propose_transformation_handler(
            dataset_id=dataset_id,
            operations=operations,
            rationale=rationale,
            version_number=version_number,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 7: prepare_release
    # =========================================================================
    @server.tool(
        name="prepare_release",
        description="Stage a verified release package, computing cryptographic hash and evidence baseline.",
    )
    def prepare_release(
        dataset_id: str,
        source_version_number: int = 1,
        destination_target: str = "s3://analytics-export",
        release_notes: Optional[str] = None,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Stage a release package."""
        result = prepare_release_handler(
            dataset_id=dataset_id,
            source_version_number=source_version_number,
            destination_target=destination_target,
            release_notes=release_notes,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 8: submit_for_review
    # =========================================================================
    @server.tool(
        name="submit_for_review",
        description="Submit a staged release package to the governance queue for Human and Challenger AI review.",
    )
    def submit_for_review(
        dataset_id: str,
        version_number: int = 1,
        staged_release_id: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Submit release for governance review."""
        result = submit_for_review_handler(
            dataset_id=dataset_id,
            version_number=version_number,
            staged_release_id=staged_release_id,
            reviewer_notes=reviewer_notes,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 9: get_approval_status
    # =========================================================================
    @server.tool(
        name="get_approval_status",
        description="Query the review, approval, or blocking status of a release package.",
    )
    def get_approval_status(
        release_id: str,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Get approval status of a release."""
        result = get_approval_status_handler(
            release_id=release_id,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 10: publish_dataset
    # =========================================================================
    @server.tool(
        name="publish_dataset",
        description="Publish dataset to destination target. MANDATORY: Requires authentic human approval token cryptographically bound to artifact hash.",
    )
    def publish_dataset(
        release_id: str,
        approval_token: str,
        expected_artifact_hash: str,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Publish dataset with human approval verification."""
        result = publish_dataset_handler(
            release_id=release_id,
            approval_token=approval_token,
            expected_artifact_hash=expected_artifact_hash,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 11: verify_publication
    # =========================================================================
    @server.tool(
        name="verify_publication",
        description="Verify destination integrity and content hash match for a published release.",
    )
    def verify_publication(
        release_id: str,
        destination_target: Optional[str] = None,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Verify publication integrity."""
        result = verify_publication_handler(
            release_id=release_id,
            destination_target=destination_target,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # TOOL 12: withdraw_release
    # =========================================================================
    @server.tool(
        name="withdraw_release",
        description="Recall or cancel a staged, pending, or published release with mandatory audit justification.",
    )
    def withdraw_release(
        release_id: str,
        reason: str,
        organization_id: Optional[str] = None,
        caller_role: str = "STEWARD",
    ) -> str:
        """Withdraw or cancel a release."""
        result = withdraw_release_handler(
            release_id=release_id,
            reason=reason,
            organization_id=organization_id,
            caller_role=caller_role,
            service=srv,
        )
        return json.dumps(result, indent=2)

    # =========================================================================
    # RESOURCES (4 Frozen Resources)
    # =========================================================================
    @server.resource(
        "releasegate://policies/current",
        description="Current release governance policy rules, weights, and risk bands.",
    )
    def get_policies_current() -> str:
        return read_policies_current(service=srv)

    @server.resource(
        "releasegate://datasets/{id}/profile",
        description="Sanitized dataset profile without raw data rows.",
    )
    def get_profile(id: str) -> str:
        return read_dataset_profile(dataset_id=id, service=srv)

    @server.resource(
        "releasegate://releases/{id}/evidence",
        description="Cryptographic release evidence ledger and provenance records.",
    )
    def get_evidence(id: str) -> str:
        return read_release_evidence(release_id=id, service=srv)

    @server.resource(
        "releasegate://system/status",
        description="System health, plane isolation status, and engine versions.",
    )
    def get_status() -> str:
        return read_system_status(service=srv)

    # =========================================================================
    # PROMPTS (4 Frozen Prompts)
    # =========================================================================
    @server.prompt(
        name="triage_dataset",
        description="Initial dataset inspection, structural profiling, and risk triage.",
    )
    def triage_dataset(dataset_id: str, version_number: int = 1) -> str:
        return render_triage_dataset_prompt(dataset_id=dataset_id, version_number=version_number)

    @server.prompt(
        name="investigate_findings",
        description="Deep-dive analysis of PII and quality findings without raw values.",
    )
    def investigate_findings(dataset_id: str, version_number: int = 1) -> str:
        return render_investigate_findings_prompt(dataset_id=dataset_id, version_number=version_number)

    @server.prompt(
        name="propose_remediation",
        description="Formulate safe, allowlisted transformations to mitigate risks.",
    )
    def propose_remediation(dataset_id: str, version_number: int = 1) -> str:
        return render_propose_remediation_prompt(dataset_id=dataset_id, version_number=version_number)

    @server.prompt(
        name="challenger_review",
        description="Independent Challenger AI model audit of evidence before human authorization.",
    )
    def challenger_review(release_id: str) -> str:
        return render_challenger_review_prompt(release_id=release_id)

    return server


# Default server instance
app = create_mcp_server()


if __name__ == "__main__":
    # When executed directly, run MCP server using standard I/O transport
    app.run()
