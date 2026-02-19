"""Top-level Agentic Schema Definition container."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema
from ninja_core.schema.relationship import RelationshipSchema


class AgenticSchema(BaseModel):
    """Top-level ASD container — the full project definition.

    This is what gets serialized to / deserialized from `.ninjastack/schema.json`.
    """

    version: str = Field(default="1.0", description="ASD schema version.")
    project_name: str = Field(min_length=1, description="Project name.")
    entities: list[EntitySchema] = Field(default_factory=list, description="All entity definitions.")
    relationships: list[RelationshipSchema] = Field(default_factory=list, description="All relationship definitions.")
    domains: list[DomainSchema] = Field(default_factory=list, description="Domain groupings.")
    description: str | None = Field(default=None, description="Project description.")

    model_config = {"extra": "forbid"}
