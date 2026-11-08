"""MCP publication tool handlers (tools 10–11).

``publish_dataset`` never creates an approval. It forwards an opaque approval
identifier to the service, which verifies the human approval record that the
out-of-band human approval channel created.
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_server.schemas.tools import PublishDatasetArgs, VerifyPublicationArgs
from mcp_server.security.permissions import MCPPrincipal
from mcp_server.service_interface import ReleaseGateService


def publish_dataset(
    args: PublishDatasetArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.publish_dataset(
        organization_id=principal.organization_id,
        release_id=args.release_id,
        approval_id=args.approval_id,
        expected_artifact_hash=args.expected_artifact_hash,
    )


def verify_publication(
    args: VerifyPublicationArgs, principal: MCPPrincipal, service: ReleaseGateService
) -> Dict[str, Any]:
    return service.verify_publication(
        organization_id=principal.organization_id,
        release_id=args.release_id,
        destination_target=args.destination_target,
    )


__all__ = ["publish_dataset", "verify_publication"]
