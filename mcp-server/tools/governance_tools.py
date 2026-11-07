"""
MCP Governance Tools (Tools 8, 9, and 12).
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.
8. submit_for_review
9. get_approval_status
12. withdraw_release
"""

import time
from typing import Any, Dict, Optional

from mcp_server.schemas.tools import (
    GetApprovalStatusArgs,
    SubmitForReviewArgs,
    WithdrawReleaseArgs,
)
from mcp_server.security.audit import audit_logger
from mcp_server.security.permissions import verify_tool_permission
from mcp_server.service_interface import ReleaseGateService, default_service


def submit_for_review_handler(
    dataset_id: str,
    version_number: int = 1,
    staged_release_id: Optional[str] = None,
    reviewer_notes: Optional[str] = None,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Submit a staged release into the governance queue for independent review.
    Validates arguments with SubmitForReviewArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "submit_for_review"
    srv = service or default_service

    # 1. Enforce strict Pydantic argument validation
    args = SubmitForReviewArgs(
        dataset_id=dataset_id,
        version_number=version_number,
        staged_release_id=staged_release_id,
        reviewer_notes=reviewer_notes,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.submit_for_review(
            dataset_id=args.dataset_id,
            version_number=args.version_number,
            staged_release_id=args.staged_release_id,
            reviewer_notes=args.reviewer_notes,
            organization_id=args.organization_id,
        )
        duration = (time.perf_counter() - t0) * 1000.0
        audit_logger.record_tool_call(
            tool_name=tool_name,
            caller_role=caller_role,
            arguments=args.model_dump(),
            success=True,
            duration_ms=duration,
        )
        return result
    except Exception as exc:
        duration = (time.perf_counter() - t0) * 1000.0
        audit_logger.record_tool_call(
            tool_name=tool_name,
            caller_role=caller_role,
            arguments=args.model_dump(),
            success=False,
            error_message=str(exc),
            duration_ms=duration,
        )
        raise


def get_approval_status_handler(
    release_id: str,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Query the review, approval, or blocking status of a release.
    Validates arguments with GetApprovalStatusArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "get_approval_status"
    srv = service or default_service

    # 1. Enforce strict Pydantic argument validation
    args = GetApprovalStatusArgs(
        release_id=release_id,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.get_approval_status(
            release_id=args.release_id,
            organization_id=args.organization_id,
        )
        duration = (time.perf_counter() - t0) * 1000.0
        audit_logger.record_tool_call(
            tool_name=tool_name,
            caller_role=caller_role,
            arguments=args.model_dump(),
            success=True,
            duration_ms=duration,
        )
        return result
    except Exception as exc:
        duration = (time.perf_counter() - t0) * 1000.0
        audit_logger.record_tool_call(
            tool_name=tool_name,
            caller_role=caller_role,
            arguments=args.model_dump(),
            success=False,
            error_message=str(exc),
            duration_ms=duration,
        )
        raise


def withdraw_release_handler(
    release_id: str,
    reason: str,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Cancel, recall, or withdraw a staged or published release package.
    Validates arguments with WithdrawReleaseArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "withdraw_release"
    srv = service or default_service

    # 1. Enforce strict Pydantic argument validation
    args = WithdrawReleaseArgs(
        release_id=release_id,
        reason=reason,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.withdraw_release(
            release_id=args.release_id,
            reason=args.reason,
            organization_id=args.organization_id,
        )
        duration = (time.perf_counter() - t0) * 1000.0
        audit_logger.record_tool_call(
            tool_name=tool_name,
            caller_role=caller_role,
            arguments=args.model_dump(),
            success=True,
            duration_ms=duration,
        )
        return result
    except Exception as exc:
        duration = (time.perf_counter() - t0) * 1000.0
        audit_logger.record_tool_call(
            tool_name=tool_name,
            caller_role=caller_role,
            arguments=args.model_dump(),
            success=False,
            error_message=str(exc),
            duration_ms=duration,
        )
        raise
