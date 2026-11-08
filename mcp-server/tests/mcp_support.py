"""Shared fixtures and helpers for the ReleaseGate MCP integration tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from local_worker.secure_storage import LocalDatasetStorage
from mcp_server.security.permissions import ClientChannel, MCPPrincipal, ToolRole
from mcp_server.server import create_mcp_server
from mcp_server.service_interface import ReleaseGateService

ORG_A = "org-alpha"
ORG_B = "org-beta"
PRINCIPAL_A = "agent-primary"
PRINCIPAL_B = "agent-other"

DIRTY_CSV = (
    "id,full_name,email_address,phone_number,income,registration_date\n"
    "1,Alice Smith,alice@example.com,555-010-1234,75000,2023-01-15\n"
    "2,Bob Jones,bob@workplace.org,555-010-5678,82000,2023-02-20\n"
    "3,Charlie Brown,charlie@test.net,555-010-9012,,2023-03-25\n"
    "4,Diana Prince,diana@themyscira.gov,555-010-3456,120000,invalid-date\n"
    "5,Evan Wright,evan@corp.com,555-010-7890,65000,2023-05-10\n"
).encode("utf-8")

CLEAN_CSV = (
    "record_id,region_code,amount\n"
    "1,FR-01,10\n"
    "2,DE-02,20\n"
    "3,IT-03,30\n"
).encode("utf-8")

RAW_VALUES = (
    "alice@example.com",
    "bob@workplace.org",
    "charlie@test.net",
    "diana@themyscira.gov",
    "evan@corp.com",
    "555-010-1234",
    "555-010-5678",
    "Alice Smith",
    "Diana Prince",
)


@dataclass
class Seeded:
    service: ReleaseGateService
    dirty_id: str
    clean_id: str


@pytest.fixture
def seeded(tmp_path) -> Seeded:
    """A service with one PII-bearing and one clean dataset for org-alpha."""
    service = ReleaseGateService(
        storage=LocalDatasetStorage(base_dir=tmp_path),
        pseudonym_secret="mcp-test-pseudonym-secret",
    )
    dirty_id = "11111111-1111-4111-8111-111111111111"
    clean_id = "22222222-2222-4222-8222-222222222222"
    service.register_dataset_artifact(
        organization_id=ORG_A,
        dataset_id=dirty_id,
        content=DIRTY_CSV,
        name="Customer records",
        description="PII-bearing customer analytics dataset",
    )
    service.register_dataset_artifact(
        organization_id=ORG_A,
        dataset_id=clean_id,
        content=CLEAN_CSV,
        name="City totals",
        description="Aggregate city totals with no direct identifiers",
    )
    return Seeded(service=service, dirty_id=dirty_id, clean_id=clean_id)


def make_principal(
    role: ToolRole = ToolRole.STEWARD,
    organization_id: str = ORG_A,
    principal_id: str = PRINCIPAL_A,
    channel: ClientChannel = ClientChannel.AI_AGENT,
) -> MCPPrincipal:
    return MCPPrincipal(
        principal_id=principal_id,
        organization_id=organization_id,
        role=role,
        channel=channel,
    )


def make_server(seeded: Seeded, role: ToolRole = ToolRole.STEWARD, organization_id: str = ORG_A):
    return create_mcp_server(
        service=seeded.service,
        principal=make_principal(role=role, organization_id=organization_id),
    )


@asynccontextmanager
async def mcp_client(server) -> AsyncIterator[ClientSession]:
    async with create_connected_server_and_client_session(server) as session:
        await session.initialize()
        # Populate the SDK tool cache so input-schema validation runs server-side.
        await session.list_tools()
        yield session


def payload(result) -> Dict[str, Any]:
    assert not result.isError, result.content[0].text if result.content else "tool error"
    return json.loads(result.content[0].text)


def error_text(result) -> str:
    assert result.isError, "expected an MCP error result"
    return result.content[0].text


async def call_tool(session: ClientSession, name: str, arguments: Dict[str, Any]):
    return await session.call_tool(name, arguments)


async def call_json(session: ClientSession, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return payload(await call_tool(session, name, arguments))


async def call_error(session: ClientSession, name: str, arguments: Dict[str, Any]) -> str:
    return error_text(await call_tool(session, name, arguments))


async def read_resource(session: ClientSession, uri: str) -> Dict[str, Any]:
    result = await session.read_resource(uri)
    return json.loads(result.contents[0].text)


async def prepare_and_submit(
    session: ClientSession,
    dataset_id: str,
    destination: str = "s3://release-evidence/exports",
) -> Dict[str, Any]:
    prepared = await call_json(
        session,
        "prepare_release",
        {"dataset_id": dataset_id, "destination_target": destination},
    )
    return await call_json(
        session,
        "submit_for_review",
        {
            "dataset_id": dataset_id,
            "version_number": prepared["version_number"],
            "staged_release_id": prepared["release_id"],
            "reviewer_notes": "Ready for independent challenger review",
        },
    )


def names(items: List[Any]) -> List[str]:
    return [getattr(item, "name", None) or getattr(item, "uriTemplate", None) for item in items]
