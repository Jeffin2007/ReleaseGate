"""
Append-only, sanitized audit ledger for MCP tool invocations.

The ledger is local and in-memory in this process; production deployments ship
the records to the cloud control plane's append-only audit store through the
authenticated outbound job channel. This module never touches PostgreSQL or the
filesystem, and every argument and error string is scrubbed before storage.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import uuid

from mcp_server.security.permissions import MCPPrincipal
from mcp_server.security.redaction import sanitize_for_audit

_MAX_RECORDS = 5_000


class MCPAuditLogger:
    """Bounded, thread-safe, sanitized audit ledger."""

    def __init__(self, max_records: int = _MAX_RECORDS) -> None:
        self._max_records = max_records
        self._records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def record_tool_call(
        self,
        *,
        tool_name: str,
        principal: MCPPrincipal,
        arguments: Dict[str, Any],
        success: bool,
        error_message: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> Dict[str, Any]:
        """Record a sanitized tool invocation."""
        record: Dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "mcp_tool_invocation",
            "tool_name": tool_name,
            "principal_id": principal.principal_id,
            "organization_id": principal.organization_id,
            "caller_role": principal.role.value,
            "channel": principal.channel.value,
            "arguments": sanitize_for_audit(arguments),
            "success": success,
            "duration_ms": round(duration_ms, 2),
        }
        if error_message:
            record["error"] = sanitize_for_audit(error_message)

        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_records:
                del self._records[: len(self._records) - self._max_records]
        return record

    def get_recent_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent audit records."""
        with self._lock:
            return list(self._records[-limit:])

    def clear(self) -> None:
        """Clear the local ledger (used by tests and controlled rotation)."""
        with self._lock:
            self._records.clear()


audit_logger = MCPAuditLogger()

__all__ = ["MCPAuditLogger", "audit_logger"]
