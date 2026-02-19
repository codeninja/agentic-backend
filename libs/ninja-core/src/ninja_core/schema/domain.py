"""Domain schema definitions for the Agentic Schema Definition."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ninja_core.schema.agent import AgentConfig


class DomainSchema(BaseModel):
    """Logical grouping of entities under one Expert Agent domain."""

    name: str = Field(min_length=1, description="Domain name (e.g. 'Inventory', 'Users').")
    entities: list[str] = Field(min_length=1, description="Entity names belonging to this domain.")
    agent_config: AgentConfig = Field(
        default_factory=AgentConfig,
        description="Agent configuration for the domain's Expert Agent.",
    )
    description: str | None = Field(default=None, description="Human-readable description.")

    model_config = {"extra": "forbid"}
