"""
Server-side identity, RBAC, and publication authorization rules.

Security invariant: the caller's role, principal, and organization are bound to
the MCP server process when it starts. They are NEVER accepted as tool
arguments, so an LLM (or a prompt-injected instruction) cannot escalate its own
privileges or cross a tenant boundary by supplying ``caller_role`` or
``organization_id``.

Publication invariant: no MCP tool can mint a human approval. ``publish_dataset``
only accepts an opaque approval identifier that a human approval channel created
out-of-band; see ``mcp_server.security.approvals``.
"""

from __future__ import annotations

import os
import re
from enum import Enum
from typing import Dict, Mapping, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


class ToolRole(str, Enum):
    """RBAC roles bound to an MCP server session."""

    ADMIN = "ADMIN"
    STEWARD = "STEWARD"
    AUDITOR = "AUDITOR"
    USER = "USER"


class ClientChannel(str, Enum):
    """Channel that owns the MCP session."""

    AI_AGENT = "AI_AGENT"
    HUMAN_OPERATOR = "HUMAN_OPERATOR"


class MCPPermissionError(Exception):
    """Raised when an MCP client may not perform the requested operation."""


class HumanApprovalRequiredError(MCPPermissionError):
    """Raised when publication is attempted without a valid human approval record."""


class MCPConfigurationError(Exception):
    """Raised when the server cannot establish a trustworthy principal."""


class MCPPrincipal(BaseModel):
    """Identity of the MCP session, resolved server-side at startup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(min_length=1, max_length=128)
    organization_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
        description="Tenant organization that scopes every dataset and release",
    )
    role: ToolRole
    channel: ClientChannel = ClientChannel.AI_AGENT


# Explicit least-privilege allowlists. A tool that is absent is denied.
ROLE_TOOL_PERMISSIONS: Dict[ToolRole, Set[str]] = {
    ToolRole.USER: {
        "inspect_dataset",
        "detect_sensitive_data",
        "validate_data_quality",
        "check_release_policy",
        "generate_risk_report",
        "propose_transformation",
        "prepare_release",
        "submit_for_review",
        "get_approval_status",
    },
    ToolRole.AUDITOR: {
        "inspect_dataset",
        "detect_sensitive_data",
        "validate_data_quality",
        "check_release_policy",
        "generate_risk_report",
        "get_approval_status",
        "verify_publication",
    },
    ToolRole.STEWARD: {
        "inspect_dataset",
        "detect_sensitive_data",
        "validate_data_quality",
        "check_release_policy",
        "generate_risk_report",
        "propose_transformation",
        "prepare_release",
        "submit_for_review",
        "get_approval_status",
        "publish_dataset",
        "verify_publication",
        "withdraw_release",
    },
    ToolRole.ADMIN: {
        "inspect_dataset",
        "detect_sensitive_data",
        "validate_data_quality",
        "check_release_policy",
        "generate_risk_report",
        "propose_transformation",
        "prepare_release",
        "submit_for_review",
        "get_approval_status",
        "publish_dataset",
        "verify_publication",
        "withdraw_release",
    },
}

# Read access for MCP resources, per role.
ROLE_RESOURCE_PERMISSIONS: Dict[ToolRole, Set[str]] = {
    ToolRole.USER: {"policies", "system_status", "dataset_profile", "release_evidence"},
    ToolRole.AUDITOR: {"policies", "system_status", "dataset_profile", "release_evidence"},
    ToolRole.STEWARD: {"policies", "system_status", "dataset_profile", "release_evidence"},
    ToolRole.ADMIN: {"policies", "system_status", "dataset_profile", "release_evidence"},
}


def has_tool_permission(role: ToolRole, tool_name: str) -> bool:
    """Return whether a role may execute a tool."""
    return tool_name in ROLE_TOOL_PERMISSIONS.get(role, set())


def verify_tool_permission(tool_name: str, principal: MCPPrincipal) -> None:
    """Raise ``MCPPermissionError`` unless the session principal may run the tool."""
    if not isinstance(principal, MCPPrincipal):
        raise MCPPermissionError("Missing authenticated MCP principal.")
    if not has_tool_permission(principal.role, tool_name):
        raise MCPPermissionError(
            f"Permission denied: role '{principal.role.value}' is not authorized "
            f"to execute tool '{tool_name}'."
        )


def verify_resource_permission(resource_kind: str, principal: MCPPrincipal) -> None:
    """Raise ``MCPPermissionError`` unless the principal may read the resource."""
    if resource_kind not in ROLE_RESOURCE_PERMISSIONS.get(principal.role, set()):
        raise MCPPermissionError(
            f"Permission denied: role '{principal.role.value}' is not authorized "
            f"to read resource '{resource_kind}'."
        )


_ENV_PRINCIPAL_ID = "RELEASEGATE_MCP_PRINCIPAL_ID"
_ENV_ORGANIZATION_ID = "RELEASEGATE_MCP_ORGANIZATION_ID"
_ENV_ROLE = "RELEASEGATE_MCP_ROLE"
_ENV_CHANNEL = "RELEASEGATE_MCP_CHANNEL"

_ORG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def resolve_principal_from_env(env: Optional[Mapping[str, str]] = None) -> MCPPrincipal:
    """
    Build the principal from the authenticated launch context.

    The local worker starts this process only after it has authenticated the
    signed job. Missing configuration fails closed: the server refuses to start
    without an explicit identity, organization, and role.
    """
    source = env if env is not None else os.environ
    principal_id = (source.get(_ENV_PRINCIPAL_ID) or "").strip()
    organization_id = (source.get(_ENV_ORGANIZATION_ID) or "").strip()
    role = (source.get(_ENV_ROLE) or "").strip().upper()
    channel = (source.get(_ENV_CHANNEL) or ClientChannel.AI_AGENT.value).strip().upper()

    missing = [
        name
        for name, value in (
            (_ENV_PRINCIPAL_ID, principal_id),
            (_ENV_ORGANIZATION_ID, organization_id),
            (_ENV_ROLE, role),
        )
        if not value
    ]
    if missing:
        raise MCPConfigurationError(
            "MCP server cannot start without an authenticated session identity. "
            f"Missing required environment variables: {', '.join(missing)}."
        )

    if not _ORG_PATTERN.fullmatch(organization_id):
        raise MCPConfigurationError("RELEASEGATE_MCP_ORGANIZATION_ID is not a valid organization id.")
    try:
        parsed_role = ToolRole(role)
    except ValueError as exc:
        raise MCPConfigurationError(
            "RELEASEGATE_MCP_ROLE must be one of ADMIN, STEWARD, AUDITOR, USER."
        ) from exc
    try:
        parsed_channel = ClientChannel(channel)
    except ValueError as exc:
        raise MCPConfigurationError(
            "RELEASEGATE_MCP_CHANNEL must be AI_AGENT or HUMAN_OPERATOR."
        ) from exc

    return MCPPrincipal(
        principal_id=principal_id,
        organization_id=organization_id,
        role=parsed_role,
        channel=parsed_channel,
    )


__all__ = [
    "ClientChannel",
    "HumanApprovalRequiredError",
    "MCPConfigurationError",
    "MCPPermissionError",
    "MCPPrincipal",
    "ROLE_RESOURCE_PERMISSIONS",
    "ROLE_TOOL_PERMISSIONS",
    "ToolRole",
    "has_tool_permission",
    "resolve_principal_from_env",
    "verify_resource_permission",
    "verify_tool_permission",
]
