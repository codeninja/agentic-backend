"""Domain schema definitions for the Agentic Schema Definition."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ninja_core.schema.agent import AgentConfig
from ninja_core.schema.entity import validate_safe_name


class DomainSchema(BaseModel):
    """Logical grouping of entities under one Expert Agent domain."""

    name: str = Field(min_length=1, description="Domain name (e.g. 'Inventory', 'Users').")

    @field_validator("name")
    @classmethod
    def validate_name_safe(cls, v: str) -> str:
        """Reject domain names containing template-injection or XSS characters."""
        return validate_safe_name(v, "Domain name")
    entities: list[str] = Field(min_length=1, description="Entity names belonging to this domain.")
    agent_config: AgentConfig = Field(
        default_factory=AgentConfig,
        description="Agent configuration for the domain's Expert Agent.",
    )
    description: str | None = Field(default=None, description="Human-readable description.")

    model_config = {"extra": "forbid"}
