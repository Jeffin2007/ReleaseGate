"""
MCP resource handlers for the four frozen ReleaseGate resources.

Resources are read-only projections of service data. Dataset and release URIs
are organization-scoped by the server-bound principal, so an MCP client cannot
read another tenant's profile or evidence by guessing an identifier.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from mcp.types import Resource, ResourceTemplate

from mcp_server.schemas.resources import (
    DatasetProfileResourceArgs,
    ReleaseEvidenceResourceArgs,
)
from mcp_server.security.permissions import MCPPrincipal, verify_resource_permission
from mcp_server.security.redaction import enforce_cloud_safe
from mcp_server.service_interface import ReleaseGateService

JSON_MIME = "application/json"

STATIC_RESOURCES = (
    Resource(
        uri="releasegate://policies/current",
        name="Current release policy",
        description="Active release policy version, weights, risk bands, and authorization rules.",
        mimeType=JSON_MIME,
    ),
    Resource(
        uri="releasegate://system/status",
        name="System status",
        description="Health, plane isolation, and local engine versions.",
        mimeType=JSON_MIME,
    ),
)

RESOURCE_TEMPLATES = (
    ResourceTemplate(
        uriTemplate="releasegate://datasets/{dataset_id}/profile",
        name="Dataset profile",
        description="Sanitized schema, null, and cardinality profile for a dataset version.",
        mimeType=JSON_MIME,
    ),
    ResourceTemplate(
        uriTemplate="releasegate://releases/{release_id}/evidence",
        name="Release evidence",
        description="Hash-bound release evidence, policy risk, approvals, and provenance.",
        mimeType=JSON_MIME,
    ),
)

_DATASET_PROFILE_URI = re.compile(
    r"^releasegate://datasets/(?P<dataset_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/profile$"
)
_RELEASE_EVIDENCE_URI = re.compile(
    r"^releasegate://releases/(?P<release_id>rel_[0-9a-f]{12})/evidence$"
)


@dataclass(frozen=True)
class ResourceRequest:
    kind: str
    arguments: Dict[str, Any]


def resolve_resource_uri(uri: str) -> ResourceRequest:
    """Map a resource URI to a permission kind and strict argument payload."""
    normalized = str(uri).strip()
    if normalized == "releasegate://policies/current":
        return ResourceRequest(kind="policies", arguments={})
    if normalized == "releasegate://system/status":
        return ResourceRequest(kind="system_status", arguments={})

    match = _DATASET_PROFILE_URI.match(normalized)
    if match:
        args = DatasetProfileResourceArgs(dataset_id=match.group("dataset_id"))
        return ResourceRequest(kind="dataset_profile", arguments=args.model_dump())

    match = _RELEASE_EVIDENCE_URI.match(normalized)
    if match:
        args = ReleaseEvidenceResourceArgs(release_id=match.group("release_id"))
        return ResourceRequest(kind="release_evidence", arguments=args.model_dump())

    raise ValueError(f"Unknown resource URI: {normalized}")


def read_resource(
    *,
    uri: str,
    principal: MCPPrincipal,
    service: ReleaseGateService,
) -> str:
    """Read one resource as a cloud-safe JSON document."""
    request = resolve_resource_uri(uri)
    verify_resource_permission(request.kind, principal)

    if request.kind == "policies":
        payload: Dict[str, Any] = service.get_current_policy()
    elif request.kind == "system_status":
        payload = service.get_system_status()
    elif request.kind == "dataset_profile":
        payload = service.get_dataset_profile(
            organization_id=principal.organization_id,
            dataset_id=request.arguments["dataset_id"],
        )
    elif request.kind == "release_evidence":
        payload = service.get_release_evidence(
            organization_id=principal.organization_id,
            release_id=request.arguments["release_id"],
        )
    else:  # pragma: no cover - guarded by resolve_resource_uri
        raise ValueError("Unsupported resource kind.")

    enforce_cloud_safe(payload)
    return json.dumps(payload, indent=2)


__all__ = [
    "RESOURCE_TEMPLATES",
    "STATIC_RESOURCES",
    "ResourceRequest",
    "read_resource",
    "resolve_resource_uri",
]
