"""Strict schemas for MCP resource arguments."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StrictResourceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetProfileResourceArgs(StrictResourceArguments):
    """Arguments for releasegate://datasets/{id}/profile."""

    dataset_id: UUID = Field(description="Registered dataset UUID")


class ReleaseEvidenceResourceArgs(StrictResourceArguments):
    """Arguments for releasegate://releases/{id}/evidence."""

    release_id: Annotated[
        str, StringConstraints(pattern=r"^rel_[0-9a-f]{12}$")
    ] = Field(description="Release identifier")


__all__ = [
    "DatasetProfileResourceArgs",
    "ReleaseEvidenceResourceArgs",
]
