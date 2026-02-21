"""Top-level Agentic Schema Definition container."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema, validate_safe_name
from ninja_core.schema.relationship import RelationshipSchema, RelationshipType


class AgenticSchema(BaseModel):
    """Top-level ASD container — the full project definition.

    This is what gets serialized to / deserialized from `.ninjastack/schema.json`.
    """

    version: str = Field(default="1.0", description="ASD schema version.")
    project_name: str = Field(min_length=1, description="Project name.")

    @field_validator("project_name")
    @classmethod
    def validate_project_name_safe(cls, v: str) -> str:
        """Reject project names containing template-injection or XSS characters."""
        return validate_safe_name(v, "Project name")
    entities: list[EntitySchema] = Field(default_factory=list, description="All entity definitions.")
    relationships: list[RelationshipSchema] = Field(default_factory=list, description="All relationship definitions.")
    domains: list[DomainSchema] = Field(default_factory=list, description="Domain groupings.")
    description: str | None = Field(default=None, description="Project description.")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> AgenticSchema:
        """Validate all cross-entity references in the schema."""
        entity_names = {e.name for e in self.entities}
        entity_fields: dict[str, set[str]] = {
            e.name: {f.name for f in e.fields} for e in self.entities
        }

        # Unique entity names
        if len(entity_names) != len(self.entities):
            seen: set[str] = set()
            for e in self.entities:
                if e.name in seen:
                    raise ValueError(f"Duplicate entity name '{e.name}'")
                seen.add(e.name)

        # Unique relationship names
        rel_names: set[str] = set()
        for rel in self.relationships:
            if rel.name in rel_names:
                raise ValueError(f"Duplicate relationship name '{rel.name}'")
            rel_names.add(rel.name)

        # Unique domain names
        domain_names: set[str] = set()
        for dom in self.domains:
            if dom.name in domain_names:
                raise ValueError(f"Duplicate domain name '{dom.name}'")
            domain_names.add(dom.name)

        # Relationship entity references
        for rel in self.relationships:
            if rel.source_entity not in entity_names:
                raise ValueError(
                    f"Relationship '{rel.name}' references non-existent "
                    f"source entity '{rel.source_entity}'"
                )
            if rel.target_entity not in entity_names:
                raise ValueError(
                    f"Relationship '{rel.name}' references non-existent "
                    f"target entity '{rel.target_entity}'"
                )

            # FK field existence check
            if rel.source_field and rel.source_field not in entity_fields[rel.source_entity]:
                raise ValueError(
                    f"Relationship '{rel.name}': source_field '{rel.source_field}' "
                    f"does not exist on entity '{rel.source_entity}'"
                )
            if rel.target_field and rel.target_field not in entity_fields[rel.target_entity]:
                raise ValueError(
                    f"Relationship '{rel.name}': target_field '{rel.target_field}' "
                    f"does not exist on entity '{rel.target_entity}'"
                )

        # Domain entity references
        for dom in self.domains:
            for ent_name in dom.entities:
                if ent_name not in entity_names:
                    raise ValueError(
                        f"Domain '{dom.name}' references non-existent "
                        f"entity '{ent_name}'"
                    )

        # Circular HARD relationship detection
        self._check_hard_relationship_cycles()

        return self

    def _check_hard_relationship_cycles(self) -> None:
        """Detect cycles in HARD relationships (self-referential allowed)."""
        # Build adjacency list for HARD relationships only, excluding self-refs
        graph: dict[str, set[str]] = {}
        for rel in self.relationships:
            if rel.relationship_type == RelationshipType.HARD:
                if rel.source_entity == rel.target_entity:
                    continue  # Self-referential is allowed
                graph.setdefault(rel.source_entity, set()).add(rel.target_entity)

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {node: WHITE for node in graph}

        def dfs(node: str) -> bool:
            """Return True if a cycle is found starting from node."""
            color[node] = GRAY
            for neighbor in graph.get(node, set()):
                if neighbor not in color:
                    color[neighbor] = WHITE
                if color[neighbor] == GRAY:
                    return True
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for node in list(graph.keys()):
            if color.get(node, WHITE) == WHITE:
                if dfs(node):
                    raise ValueError(
                        "Circular dependency detected in HARD relationships "
                        "(self-referential entities are allowed, but "
                        "A→B→...→A cycles are not)"
                    )
