"""Registry of the 12 frozen MCP tools.

Each entry binds a public tool name to its strict argument model and its
handler. The registry is the single source of truth for tool listing,
validation, and dispatch; adding a handler here is the only way to expose it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Type

from pydantic import BaseModel

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
    TOOL_ARGUMENT_MODELS,
    ValidateDataQualityArgs,
    VerifyPublicationArgs,
    WithdrawReleaseArgs,
)
from mcp_server.security.permissions import MCPPrincipal
from mcp_server.service_interface import ReleaseGateService
from mcp_server.tools import (
    governance_tools,
    inspection_tools,
    publication_tools,
    transformation_tools,
)


ToolHandler = Callable[[Any, MCPPrincipal, ReleaseGateService], Dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    """Definition of one MCP tool."""

    name: str
    description: str
    args_model: Type[BaseModel]
    handler: ToolHandler


TOOL_SPECS: Dict[str, ToolSpec] = {
    "inspect_dataset": ToolSpec(
        name="inspect_dataset",
        description=(
            "Profile a registered dataset locally and return the sanitized governance "
            "report: schema, null distributions, PII summary, quality summary, and "
            "100-point risk score. Never returns raw dataset values."
        ),
        args_model=InspectDatasetArgs,
        handler=inspection_tools.inspect_dataset,
    ),
    "detect_sensitive_data": ToolSpec(
        name="detect_sensitive_data",
        description=(
            "Scan a dataset locally with Microsoft Presidio. Returns entity types, "
            "affected columns, occurrence counts, severity, confidence, and sanitized "
            "evidence coordinates only."
        ),
        args_model=DetectSensitiveDataArgs,
        handler=inspection_tools.detect_sensitive_data,
    ),
    "validate_data_quality": ToolSpec(
        name="validate_data_quality",
        description=(
            "Run deterministic local data-quality rules and return aggregate pass/fail "
            "counts, quality score, and sanitized issue evidence."
        ),
        args_model=ValidateDataQualityArgs,
        handler=inspection_tools.validate_data_quality,
    ),
    "check_release_policy": ToolSpec(
        name="check_release_policy",
        description=(
            "Evaluate whether a dataset version is release-eligible under the active "
            "versioned release policy, including blocking reasons and category scores."
        ),
        args_model=CheckReleasePolicyArgs,
        handler=inspection_tools.check_release_policy,
    ),
    "generate_risk_report": ToolSpec(
        name="generate_risk_report",
        description=(
            "Produce the full structured risk assessment for a dataset version, "
            "combining profiling, privacy, quality, and weighted policy evidence."
        ),
        args_model=GenerateRiskReportArgs,
        handler=inspection_tools.generate_risk_report,
    ),
    "propose_transformation": ToolSpec(
        name="propose_transformation",
        description=(
            "Simulate an ordered list of allowlisted declarative transformations "
            "(remove, mask, pseudonymize, generalize, filter). Returns aggregate impact "
            "and a simulated output hash; original data is never modified and no code runs."
        ),
        args_model=ProposeTransformationArgs,
        handler=transformation_tools.propose_transformation,
    ),
    "prepare_release": ToolSpec(
        name="prepare_release",
        description=(
            "Stage a release package with a hash-bound evidence baseline. Staging does "
            "not publish anything and does not grant approval."
        ),
        args_model=PrepareReleaseArgs,
        handler=transformation_tools.prepare_release,
    ),
    "submit_for_review": ToolSpec(
        name="submit_for_review",
        description=(
            "Submit a staged release to the independent review queue. Human approval is "
            "still required before publication."
        ),
        args_model=SubmitForReviewArgs,
        handler=governance_tools.submit_for_review,
    ),
    "get_approval_status": ToolSpec(
        name="get_approval_status",
        description=(
            "Read the lifecycle, review, and human-approval status of a release. "
            "Never returns an approval token."
        ),
        args_model=GetApprovalStatusArgs,
        handler=governance_tools.get_approval_status,
    ),
    "publish_dataset": ToolSpec(
        name="publish_dataset",
        description=(
            "Publish a reviewed dataset to its approved destination. Requires an "
            "out-of-band human approval record bound to the exact release and artifact "
            "hash. AI cannot authorize publication."
        ),
        args_model=PublishDatasetArgs,
        handler=publication_tools.publish_dataset,
    ),
    "verify_publication": ToolSpec(
        name="verify_publication",
        description=(
            "Verify the publication state and artifact-hash integrity of a release at "
            "its destination."
        ),
        args_model=VerifyPublicationArgs,
        handler=publication_tools.verify_publication,
    ),
    "withdraw_release": ToolSpec(
        name="withdraw_release",
        description=(
            "Withdraw a staged, pending, or published release with a mandatory audit "
            "justification, revoking any outstanding human approval."
        ),
        args_model=WithdrawReleaseArgs,
        handler=governance_tools.withdraw_release,
    ),
}

# Fail closed if the registry and the schema registry ever drift apart.
if set(TOOL_SPECS) != set(TOOL_ARGUMENT_MODELS):
    raise RuntimeError("MCP tool registry and argument schema registry are out of sync.")


__all__ = ["TOOL_SPECS", "ToolSpec"]
