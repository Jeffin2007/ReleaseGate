"""
ReleaseGate MCP Resource Handlers.
Adheres to the 4 frozen MCP resources specified in Frozen Architecture Baseline v1.0:
1. releasegate://policies/current
2. releasegate://datasets/{id}/profile
3. releasegate://releases/{id}/evidence
4. releasegate://system/status
"""

import json
from typing import Any, Dict, Optional

from mcp_server.service_interface import ReleaseGateService, default_service


def read_policies_current(service: Optional[ReleaseGateService] = None) -> str:
    """Read resource: releasegate://policies/current"""
    srv = service or default_service
    policy_data = srv.get_current_policy()
    return json.dumps(policy_data, indent=2)


def read_dataset_profile(dataset_id: str, service: Optional[ReleaseGateService] = None) -> str:
    """Read resource: releasegate://datasets/{id}/profile"""
    srv = service or default_service
    profile_data = srv.get_dataset_profile(dataset_id=dataset_id)
    return json.dumps(profile_data, indent=2)


def read_release_evidence(release_id: str, service: Optional[ReleaseGateService] = None) -> str:
    """Read resource: releasegate://releases/{id}/evidence"""
    srv = service or default_service
    evidence_data = srv.get_release_evidence(release_id=release_id)
    return json.dumps(evidence_data, indent=2)


def read_system_status(service: Optional[ReleaseGateService] = None) -> str:
    """Read resource: releasegate://system/status"""
    srv = service or default_service
    status_data = srv.get_system_status()
    return json.dumps(status_data, indent=2)
