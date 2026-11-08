"""MCP governance tool handlers (tools 8, 9, and 12)."""

from __future__ import annotations

from typing import Any, Dict

from mcp_server.schemas.tools import (
    GetApprovalStatusArgs,
    SubmitForReviewArgs,
    WithdrawReleaseArgs,
)
from mcp_server.security.permissions import MCPPrincipal
from mcp_server.service_interface import ReleaseGateService


def submit_for_review(
    args: SubmitForReviewArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.submit_for_review(
        organization_id=principal.organization_id,
        dataset_id=str(args.dataset_id),
        version_number=args.version_number,
        staged_release_id=args.staged_release_id,
        reviewer_notes=args.reviewer_notes,
    )


def get_approval_status(
    args: GetApprovalStatusArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.get_approval_status(
        organization_id=principal.organization_id,
        release_id=args.release_id,
    )


def withdraw_release(
    args: WithdrawReleaseArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.withdraw_release(
        organization_id=principal.organization_id,
        release_id=args.release_id,
        reason=args.reason,
    )


__all__ = ["get_approval_status", "submit_for_review", "withdraw_release"]
