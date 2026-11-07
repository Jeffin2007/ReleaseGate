"""
MCP Inspection Tools (Tools 1 to 5).
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.
1. inspect_dataset
2. detect_sensitive_data
3. validate_data_quality
4. check_release_policy
5. generate_risk_report
"""

import time
from typing import Any, Dict, List, Optional
import json

from mcp_server.schemas.tools import (
    CheckReleasePolicyArgs,
    DetectSensitiveDataArgs,
    GenerateRiskReportArgs,
    InspectDatasetArgs,
    ValidateDataQualityArgs,
)
from mcp_server.security.audit import audit_logger
from mcp_server.security.permissions import verify_tool_permission
from mcp_server.service_interface import ReleaseGateService, default_service


def inspect_dataset_handler(
    dataset_id: str,
    version_number: int = 1,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Execute full multi-engine inspection (Profiling, Presidio PII, Quality, Policy).
    Validates arguments with InspectDatasetArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "inspect_dataset"
    srv = service or default_service

    # 1. Enforce strict Pydantic argument validation
    args = InspectDatasetArgs(
        dataset_id=dataset_id,
        version_number=version_number,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution via Service Interface
    try:
        result = srv.inspect_dataset(
            dataset_id=args.dataset_id,
            version_number=args.version_number,
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


def detect_sensitive_data_handler(
    dataset_id: str,
    version_number: int = 1,
    confidence_threshold: float = 0.6,
    entities: Optional[List[str]] = None,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Scan dataset for PII entities using Microsoft Presidio Analyzer.
    Validates arguments with DetectSensitiveDataArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "detect_sensitive_data"
    srv = service or default_service

    # 1. Strict Schema Validation
    args = DetectSensitiveDataArgs(
        dataset_id=dataset_id,
        version_number=version_number,
        confidence_threshold=confidence_threshold,
        entities=entities,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.detect_sensitive_data(
            dataset_id=args.dataset_id,
            version_number=args.version_number,
            confidence_threshold=args.confidence_threshold,
            entities=args.entities,
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


def validate_data_quality_handler(
    dataset_id: str,
    version_number: int = 1,
    allow_nulls: Optional[bool] = None,
    allow_duplicates: Optional[bool] = None,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Evaluate dataset quality rules locally and deterministically.
    Validates arguments with ValidateDataQualityArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "validate_data_quality"
    srv = service or default_service

    # 1. Strict Schema Validation
    args = ValidateDataQualityArgs(
        dataset_id=dataset_id,
        version_number=version_number,
        allow_nulls=allow_nulls,
        allow_duplicates=allow_duplicates,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.validate_data_quality(
            dataset_id=args.dataset_id,
            version_number=args.version_number,
            allow_nulls=args.allow_nulls,
            allow_duplicates=args.allow_duplicates,
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


def check_release_policy_handler(
    dataset_id: str,
    version_number: int = 1,
    policy_version: str = "1.0.0",
    domain: Optional[str] = None,
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Check dataset release readiness against 100-point release policy.
    Validates arguments with CheckReleasePolicyArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "check_release_policy"
    srv = service or default_service

    # 1. Strict Schema Validation
    args = CheckReleasePolicyArgs(
        dataset_id=dataset_id,
        version_number=version_number,
        policy_version=policy_version,
        domain=domain,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.check_release_policy(
            dataset_id=args.dataset_id,
            version_number=args.version_number,
            policy_version=args.policy_version,
            domain=args.domain,
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


def generate_risk_report_handler(
    dataset_id: str,
    version_number: int = 1,
    policy_version: str = "1.0.0",
    organization_id: Optional[str] = None,
    caller_role: str = "STEWARD",
    service: Optional[ReleaseGateService] = None,
) -> Dict[str, Any]:
    """
    Generate comprehensive risk evaluation report.
    Validates arguments with GenerateRiskReportArgs schema.
    """
    t0 = time.perf_counter()
    tool_name = "generate_risk_report"
    srv = service or default_service

    # 1. Strict Schema Validation
    args = GenerateRiskReportArgs(
        dataset_id=dataset_id,
        version_number=version_number,
        policy_version=policy_version,
        organization_id=organization_id,
    )

    # 2. RBAC Permission Check
    verify_tool_permission(tool_name, caller_role)

    # 3. Execution
    try:
        result = srv.generate_risk_report(
            dataset_id=args.dataset_id,
            version_number=args.version_number,
            policy_version=args.policy_version,
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
