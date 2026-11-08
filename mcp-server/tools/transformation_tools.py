"""MCP transformation tool handlers (tools 6–7)."""

from __future__ import annotations

from typing import Any, Dict

from mcp_server.schemas.tools import PrepareReleaseArgs, ProposeTransformationArgs
from mcp_server.security.permissions import MCPPrincipal
from mcp_server.service_interface import ReleaseGateService


def propose_transformation(
    args: ProposeTransformationArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.propose_transformation(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        version_number=args.version_number,
        operations=[operation.model_dump() for operation in args.operations],
        rationale=args.rationale,
    )


def prepare_release(
    args: PrepareReleaseArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.prepare_release(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        source_version_number=args.source_version_number,
        destination_target=args.destination_target,
        release_notes=args.release_notes,
    )


__all__ = ["prepare_release", "propose_transformation"]
