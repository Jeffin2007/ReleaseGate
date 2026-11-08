"""Strict schemas for the four frozen MCP prompt arguments."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StrictPromptArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetPromptArgs(StrictPromptArguments):
    """Arguments shared by dataset-oriented prompts."""

    dataset_id: UUID = Field(description="Registered dataset UUID")
    version_number: int = Field(default=1, ge=1, le=10000, description="Dataset version")


class ChallengerReviewPromptArgs(StrictPromptArguments):
    """Arguments for the challenger_review prompt."""

    release_id: Annotated[
        str, StringConstraints(pattern=r"^rel_[0-9a-f]{12}$")
    ] = Field(description="Release identifier under review")


__all__ = [
    "ChallengerReviewPromptArgs",
    "DatasetPromptArgs",
]
