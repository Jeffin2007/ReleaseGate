"""MCP inspection tool handlers (tools 1–5).

Handlers are deliberately thin: they translate a validated argument model into a
service call. Validation, authorization, auditing, and cloud-safety checks are
performed centrally by the MCP server before a handler runs.
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_server.schemas.tools import (
    CheckReleasePolicyArgs,
    DetectSensitiveDataArgs,
    GenerateRiskReportArgs,
    InspectDatasetArgs,
    ValidateDataQualityArgs,
)
from mcp_server.security.permissions import MCPPrincipal
from mcp_server.service_interface import ReleaseGateService


def inspect_dataset(
    args: InspectDatasetArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.inspect_dataset(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        version_number=args.version_number,
    )


def detect_sensitive_data(
    args: DetectSensitiveDataArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.detect_sensitive_data(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        version_number=args.version_number,
        confidence_threshold=float(args.confidence_threshold),
        entities=args.entities,
    )


def validate_data_quality(
    args: ValidateDataQualityArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.validate_data_quality(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        version_number=args.version_number,
        allow_nulls=args.allow_nulls,
        allow_duplicates=args.allow_duplicates,
    )


def check_release_policy(
    args: CheckReleasePolicyArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.check_release_policy(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        version_number=args.version_number,
        policy_version=args.policy_version,
        domain=args.domain,
    )


def generate_risk_report(
    args: GenerateRiskReportArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.generate_risk_report(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        version_number=args.version_number,
        policy_version=args.policy_version,
    )


__all__ = [
    "check_release_policy",
    "detect_sensitive_data",
    "generate_risk_report",
    "inspect_dataset",
    "validate_data_quality",
]
