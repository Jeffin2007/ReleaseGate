"""
MCP Publication Tools (Tools 10 and 11).
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.
10. publish_dataset
11. verify_publication

CRITICAL ARCHITECTURE REQUIREMENT:
AI is strictly prohibited from authorizing publication.
A valid human approval token cryptographically bound to the artifact hash is mandatory.
"""

import time
from typing import Any, Dict, Optional

from mcp_server.schemas.tools import (
    PublishDatasetArgs,
    VerifyPublicationArgs,
)
from mcp_server.security.audit import audit_logger
from mcp_server.security.permissions import verify_tool_permission
from mcp_server.service_interface import ReleaseGateService, default_service


def publish_dataset_handler(
    release_id: str,
    approval_token: str,
    expected_artifact_hash: str,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Publish dataset to release target.
    Requires authentic human authorization token bound to expected_artifact_hash.
    Validates arguments with PublishDatasetArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "publish_dataset"
    srv = service or default_service

    # 1. Enforce strict Pydantic argument validation
    args = PublishDatasetArgs(
        release_id=release_id,
        approval_token=approval_token,
        expected_artifact_hash=expected_artifact_hash,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.publish_dataset(
            release_id=args.release_id,
            approval_token=args.approval_token,
            expected_artifact_hash=args.expected_artifact_hash,
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


def verify_publication_handler(
    release_id: str,
    destination_target: Optional[str] = None,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Verify publication integrity and hash match at destination target.
    Validates arguments with VerifyPublicationArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "verify_publication"
    srv = service or default_service

    # 1. Enforce strict Pydantic argument validation
    args = VerifyPublicationArgs(
        release_id=release_id,
        destination_target=destination_target,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.verify_publication(
            release_id=args.release_id,
            destination_target=args.destination_target,
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
