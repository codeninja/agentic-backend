"""Domain schema definitions for the Agentic Schema Definition."""

from __future__ import annotations

import keyword
import re

from pydantic import BaseModel, Field, field_validator

from ninja_core.schema.agent import AgentConfig
from ninja_core.schema.entity import MAX_DESCRIPTION_LENGTH

# Valid identifier: starts with letter, alphanumeric + underscores, max 64 chars.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


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

    @field_validator("name")
    @classmethod
    def validate_domain_name(cls, v: str) -> str:
        """Enforce safe identifier pattern on domain names.

        Rejects names with newlines, quotes, control characters, and Python
        reserved keywords. This is the primary defense against prompt injection
        via schema metadata.
        """
        if not _IDENTIFIER_RE.match(v):
            raise ValueError(
                f"Domain name {v!r} is not a valid identifier. "
                "Must start with a letter, contain only alphanumeric characters "
                "and underscores, and be at most 64 characters."
            )
        if keyword.iskeyword(v):
            raise ValueError(f"Domain name {v!r} is a Python reserved keyword.")
        return v

    @field_validator("description")
    @classmethod
    def validate_domain_description(cls, v: str | None) -> str | None:
        """Enforce maximum length on description."""
        if v is not None and len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"Description too long ({len(v)} chars). Maximum is {MAX_DESCRIPTION_LENGTH} characters.")
        return v
