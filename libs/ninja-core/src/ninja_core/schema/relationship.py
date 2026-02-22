"""Relationship schema definitions for the Agentic Schema Definition."""

from __future__ import annotations

import warnings
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class RelationshipType(str, Enum):
    """Type of relationship between entities."""

    HARD = "hard"  # Foreign key / strict reference
    SOFT = "soft"  # Semantic / vector similarity link
    GRAPH = "graph"  # Graph edge (Neo4j-style)


class Cardinality(str, Enum):
    """Cardinality of a relationship."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class RelationshipSchema(BaseModel):
    """Schema definition for a relationship between two entities."""

    name: str = Field(min_length=1, description="Relationship name.")
    source_entity: str = Field(min_length=1, description="Source entity name.")
    target_entity: str = Field(min_length=1, description="Target entity name.")
    relationship_type: RelationshipType = Field(description="Type of link.")
    cardinality: Cardinality = Field(description="Cardinality of the relationship.")
    source_field: str | None = Field(default=None, description="FK field on source entity (for hard relationships).")
    target_field: str | None = Field(
        default=None, description="Referenced field on target entity (for hard relationships)."
    )
    edge_label: str | None = Field(default=None, description="Edge label in graph DB (for graph relationships).")
    description: str | None = Field(default=None, description="Human-readable description.")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_relationship_fields(self) -> RelationshipSchema:
        """Validate FK fields for HARD relationships and edge_label for GRAPH."""
        if self.relationship_type == RelationshipType.HARD:
            if not self.source_field or not self.target_field:
                raise ValueError(
                    f"HARD relationship '{self.name}' requires both source_field and target_field to be set"
                )

        if self.relationship_type == RelationshipType.GRAPH:
            if not self.edge_label:
                self.edge_label = self.name
                warnings.warn(
                    f"GRAPH relationship '{self.name}' has no edge_label set; "
                    f"defaulting to relationship name '{self.name}'",
                    UserWarning,
                    stacklevel=1,
                )
        return self
