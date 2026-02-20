"""ADK tool definitions that manipulate an in-memory AgenticSchema.

All tools operate on a shared ``SchemaWorkspace`` instance so they can be
tested independently of any LLM.  The ``create_adk_tools`` factory produces
bound wrapper functions suitable for passing to ``LlmAgent(tools=...)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType
from ninja_introspect.engine import IntrospectionEngine


@dataclass
class SchemaWorkspace:
    """Mutable workspace holding the in-progress ASD."""

    schema: AgenticSchema = field(default_factory=lambda: AgenticSchema(project_name="my-ninja-project"))


# ---------------------------------------------------------------------------
# Tool implementations — pure functions that accept a workspace
# ---------------------------------------------------------------------------


def add_entity(
    workspace: SchemaWorkspace,
    name: str,
    fields: list[dict[str, str]],
    storage_engine: str = "sql",
    description: str | None = None,
) -> str:
    """Add an entity to the schema.

    Args:
        workspace: The current schema workspace.
        name: Entity name (PascalCase).
        fields: List of dicts with keys ``name``, ``field_type``, and optionally
            ``primary_key``, ``nullable``, ``unique``, ``indexed``, ``description``.
        storage_engine: One of sql, mongo, graph, vector.
        description: Optional entity description.

    Returns:
        A confirmation message.
    """
    for existing in workspace.schema.entities:
        if existing.name == name:
            return f"Entity '{name}' already exists. Use a different name or remove it first."

    parsed_fields: list[FieldSchema] = []
    for f in fields:
        parsed_fields.append(
            FieldSchema(
                name=f["name"],
                field_type=FieldType(f.get("field_type", "string")),
                primary_key=_to_bool(f.get("primary_key", False)),
                nullable=_to_bool(f.get("nullable", False)),
                unique=_to_bool(f.get("unique", False)),
                indexed=_to_bool(f.get("indexed", False)),
                description=f.get("description"),
            )
        )

    entity = EntitySchema(
        name=name,
        storage_engine=StorageEngine(storage_engine),
        fields=parsed_fields,
        description=description,
    )
    workspace.schema.entities.append(entity)
    field_names = ", ".join(f.name for f in parsed_fields)
    return f"Added entity '{name}' ({storage_engine}) with fields: {field_names}"


def add_relationship(
    workspace: SchemaWorkspace,
    name: str,
    source_entity: str,
    target_entity: str,
    relationship_type: str = "hard",
    cardinality: str = "many_to_one",
    source_field: str | None = None,
    target_field: str | None = None,
    description: str | None = None,
) -> str:
    """Add a relationship between two entities.

    Returns:
        A confirmation message.
    """
    entity_names = {e.name for e in workspace.schema.entities}
    if source_entity not in entity_names:
        return f"Source entity '{source_entity}' not found. Add it first."
    if target_entity not in entity_names:
        return f"Target entity '{target_entity}' not found. Add it first."

    rel = RelationshipSchema(
        name=name,
        source_entity=source_entity,
        target_entity=target_entity,
        relationship_type=RelationshipType(relationship_type),
        cardinality=Cardinality(cardinality),
        source_field=source_field,
        target_field=target_field,
        description=description,
    )
    workspace.schema.relationships.append(rel)
    return f"Added relationship '{name}': {source_entity} -> {target_entity} ({cardinality})"


def create_domain(
    workspace: SchemaWorkspace,
    name: str,
    entities: list[str],
    description: str | None = None,
) -> str:
    """Group entities into a logical domain.

    Returns:
        A confirmation message.
    """
    entity_names = {e.name for e in workspace.schema.entities}
    missing = [e for e in entities if e not in entity_names]
    if missing:
        return f"Entities not found: {', '.join(missing)}. Add them first."

    for existing in workspace.schema.domains:
        if existing.name == name:
            return f"Domain '{name}' already exists."

    domain = DomainSchema(name=name, entities=entities, description=description)
    workspace.schema.domains.append(domain)
    return f"Created domain '{name}' with entities: {', '.join(entities)}"


def review_schema(workspace: SchemaWorkspace) -> str:
    """Return a human-readable summary of the current schema.

    Returns:
        A formatted string showing entities, relationships, and domains.
    """
    schema = workspace.schema
    lines: list[str] = [f"Project: {schema.project_name}", f"Version: {schema.version}", ""]

    if not schema.entities:
        lines.append("No entities defined yet.")
    else:
        lines.append(f"Entities ({len(schema.entities)}):")
        for entity in schema.entities:
            field_summary = ", ".join(f"{f.name}: {f.field_type.value}" for f in entity.fields)
            lines.append(f"  - {entity.name} [{entity.storage_engine.value}]: {field_summary}")

    if schema.relationships:
        lines.append(f"\nRelationships ({len(schema.relationships)}):")
        for rel in schema.relationships:
            lines.append(f"  - {rel.name}: {rel.source_entity} -> {rel.target_entity} ({rel.cardinality.value})")

    if schema.domains:
        lines.append(f"\nDomains ({len(schema.domains)}):")
        for domain in schema.domains:
            lines.append(f"  - {domain.name}: {', '.join(domain.entities)}")

    return "\n".join(lines)


def confirm_schema(workspace: SchemaWorkspace) -> str:
    """Validate and return the finalized schema as JSON.

    Returns:
        The schema JSON string, or an error message if validation fails.
    """
    schema = workspace.schema
    if not schema.entities:
        return "Cannot confirm: no entities defined yet."

    return json.dumps(schema.model_dump(), indent=2)


async def introspect_database(
    workspace: SchemaWorkspace,
    connection_string: str,
) -> str:
    """Run database introspection and merge results into the workspace schema.

    Args:
        workspace: The current schema workspace.
        connection_string: Database connection URI.

    Returns:
        A summary of discovered entities and relationships.
    """
    engine = IntrospectionEngine(project_name=workspace.schema.project_name)
    result = await engine.run([connection_string])

    new_entities = 0
    existing_names = {e.name for e in workspace.schema.entities}
    for entity in result.entities:
        if entity.name not in existing_names:
            workspace.schema.entities.append(entity)
            existing_names.add(entity.name)
            new_entities += 1

    new_rels = 0
    existing_rels = {r.name for r in workspace.schema.relationships}
    for rel in result.relationships:
        if rel.name not in existing_rels:
            workspace.schema.relationships.append(rel)
            existing_rels.add(rel.name)
            new_rels += 1

    return f"Introspection complete: discovered {new_entities} new entities and {new_rels} new relationships."


# ---------------------------------------------------------------------------
# ADK tool factory — produces bound functions for LlmAgent(tools=...)
# ---------------------------------------------------------------------------


def create_adk_tools(workspace: SchemaWorkspace) -> list[Callable[..., Any]]:
    """Create ADK-compatible tool functions bound to *workspace*.

    Each returned function has the correct signature (without ``workspace``)
    and docstring for ADK to auto-generate function declarations.
    """

    def adk_add_entity(
        name: str,
        fields: list[dict[str, str]],
        storage_engine: str = "sql",
        description: str = "",
    ) -> str:
        """Add a new entity (table/collection/node) to the schema.

        Args:
            name: Entity name in PascalCase (e.g. 'User', 'Product').
            fields: List of field definitions. Each dict must have 'name' and 'field_type' keys.
                Valid field_type values: string, text, integer, float, boolean, datetime, date,
                uuid, json, array, binary, enum.  Optional keys: primary_key, nullable, unique, indexed.
            storage_engine: Storage engine — sql, mongo, graph, or vector.  Defaults to sql.
            description: Human-readable entity description.
        """
        return add_entity(
            workspace, name=name, fields=fields, storage_engine=storage_engine, description=description or None
        )

    def adk_add_relationship(
        name: str,
        source_entity: str,
        target_entity: str,
        relationship_type: str = "hard",
        cardinality: str = "many_to_one",
        source_field: str = "",
        target_field: str = "",
        description: str = "",
    ) -> str:
        """Define a relationship between two entities.

        Args:
            name: Relationship name (e.g. 'user_posts').
            source_entity: Name of the source entity.
            target_entity: Name of the target entity.
            relationship_type: Type — hard, soft, or graph.  Defaults to hard.
            cardinality: one_to_one, one_to_many, many_to_one, or many_to_many.
            source_field: FK field on the source entity.
            target_field: Referenced field on the target entity.
            description: Relationship description.
        """
        return add_relationship(
            workspace,
            name=name,
            source_entity=source_entity,
            target_entity=target_entity,
            relationship_type=relationship_type,
            cardinality=cardinality,
            source_field=source_field or None,
            target_field=target_field or None,
            description=description or None,
        )

    def adk_create_domain(
        name: str,
        entities: list[str],
        description: str = "",
    ) -> str:
        """Group entities into a logical domain with its own Expert Agent.

        Args:
            name: Domain name (e.g. 'Users', 'Inventory').
            entities: List of entity names belonging to this domain.
            description: Domain description.
        """
        return create_domain(workspace, name=name, entities=entities, description=description or None)

    def adk_review_schema() -> str:
        """Show the current schema summary — entities, relationships, and domains."""
        return review_schema(workspace)

    def adk_confirm_schema() -> str:
        """Finalize and validate the schema. Returns the full ASD as JSON."""
        return confirm_schema(workspace)

    async def adk_introspect_database(connection_string: str) -> str:
        """Connect to a database and discover its schema via introspection.

        Args:
            connection_string: Database connection URI (e.g. postgresql://user:pass@host/db).
        """
        return await introspect_database(workspace, connection_string=connection_string)

    return [
        adk_add_entity,
        adk_add_relationship,
        adk_create_domain,
        adk_review_schema,
        adk_confirm_schema,
        adk_introspect_database,
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_bool(value: object) -> bool:
    """Coerce a value to bool (handles string 'true'/'false' from LLM)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)
