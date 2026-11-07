"""
MCP Transformation Tools (Tools 6 and 7).
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.
6. propose_transformation
7. prepare_release
"""

import time
from typing import Any, Dict, List, Optional, Union

from mcp_server.schemas.tools import (
    PrepareReleaseArgs,
    ProposeTransformationArgs,
    TransformationOperationSpec,
)
from mcp_server.security.audit import audit_logger
from mcp_server.security.permissions import verify_tool_permission
from mcp_server.service_interface import ReleaseGateService, default_service


def propose_transformation_handler(
    dataset_id: str,
    operations: List[Union[Dict[str, Any], TransformationOperationSpec]],
    rationale: str,
    version_number: int = 1,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Simulate and validate allowlisted transformations without altering original datasets.
    Validates arguments with ProposeTransformationArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "propose_transformation"
    srv = service or default_service

    # Convert dictionary operations to TransformationOperationSpec if needed
    typed_specs: List[TransformationOperationSpec] = []
    for op in operations:
        if isinstance(op, TransformationOperationSpec):
            typed_specs.append(op)
        elif isinstance(op, dict):
            typed_specs.append(TransformationOperationSpec(**op))
        else:
            raise ValueError(f"Invalid operation specification: {type(op)}")

    # 1. Enforce strict Pydantic argument validation
    args = ProposeTransformationArgs(
        dataset_id=dataset_id,
        version_number=version_number,
        operations=typed_specs,
        rationale=rationale,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        raw_ops = [op.model_dump() for op in args.operations]
        result = srv.propose_transformation(
            dataset_id=args.dataset_id,
            version_number=args.version_number,
            operations=raw_ops,
            rationale=args.rationale,
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


def prepare_release_handler(
    dataset_id: str,
    source_version_number: int = 1,
    destination_target: str = "s3://analytics-export",
    release_notes: Optional[str] = None,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Stage a release package, establishing cryptographic evidence baseline.
    Validates arguments with PrepareReleaseArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "prepare_release"
    srv = service or default_service

    # 1. Enforce strict Pydantic argument validation
    args = PrepareReleaseArgs(
        dataset_id=dataset_id,
        source_version_number=source_version_number,
        destination_target=destination_target,
        release_notes=release_notes,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.prepare_release(
            dataset_id=args.dataset_id,
            source_version_number=args.source_version_number,
            destination_target=args.destination_target,
            release_notes=args.release_notes,
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
