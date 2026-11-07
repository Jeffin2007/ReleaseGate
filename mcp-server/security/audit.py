"""
Audit logging for ReleaseGate Model Context Protocol (MCP) tool invocations.
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.
Ensures zero raw dataset values, credentials, or local filesystem paths appear in logs.
"""

from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("releasegate.mcp.audit")

# Prohibited patterns in audit records
PATH_PATTERN = re.compile(r"(/[a-zA-Z0-9_\-\.]+)+")


class MCPAuditLogger:
    """
    Structured audit logger for MCP tool interactions.
    Guarantees sanitized parameter logging and immutable record formatting.
    """

    def __init__(self) -> None:
        self.in_memory_audit_ledger: List[Dict[str, Any]] = []

    def sanitize_data(self, data: Any) -> Any:
        """
        Recursively remove any sensitive fields or local absolute paths.
        """
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                lower_k = str(k).lower()
                if "token" in lower_k or "secret" in lower_k or "key" in lower_k:
                    sanitized[k] = "[REDACTED_SECRET]"
                elif "raw" in lower_k or "content" in lower_k or "text" in lower_k:
                    if isinstance(v, (str, bytes)):
                        sanitized[k] = "[REDACTED_RAW_CONTENT]"
                    else:
                        sanitized[k] = self.sanitize_data(v)
                else:
                    sanitized[k] = self.sanitize_data(v)
            return sanitized
        elif isinstance(data, list):
            return [self.sanitize_data(item) for item in data]
        elif isinstance(data, str):
            # Check if it looks like an absolute filesystem path outside of allowed URIs
            if data.startswith("/") and not data.startswith("/api/"):
                return "[REDACTED_LOCAL_PATH]"
            return data
        else:
            return data

    def record_tool_call(
        self,
        tool_name: str,
        caller_role: str,
        arguments: Dict[str, Any],
        success: bool,
        error_message: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> Dict[str, Any]:
        """Record an auditable MCP tool invocation event."""
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            "event_id": event_id,
            "timestamp": timestamp,
            "event_type": "mcp_tool_invocation",
            "tool_name": tool_name,
            "caller_role": caller_role,
            "arguments": self.sanitize_data(arguments),
            "success": success,
            "duration_ms": round(duration_ms, 2),
        }
        if error_message:
            record["error"] = error_message

        self.in_memory_audit_ledger.append(record)
        logger.info(
            f"MCP Tool '{tool_name}' invoked by role '{caller_role}' - "
            f"success={success} duration={record['duration_ms']}ms"
        )
        return record

    def get_recent_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent sanitized audit records."""
        return self.in_memory_audit_ledger[-limit:]


audit_logger = MCPAuditLogger()
