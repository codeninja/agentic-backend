"""ADK tool definitions that manipulate an in-memory AgenticSchema.

All tools operate on a shared ``SchemaWorkspace`` instance so they can be
tested independently of any LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

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
# Helpers
# ---------------------------------------------------------------------------


def _to_bool(value: object) -> bool:
    """Coerce a value to bool (handles string 'true'/'false' from LLM)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


# ---------------------------------------------------------------------------
# ADK tool descriptors — used by the agent to register callable tools.
# Each descriptor is a dict compatible with Google ADK's FunctionDeclaration.
# ---------------------------------------------------------------------------


TOOL_DECLARATIONS = [
    {
        "name": "add_entity",
        "description": (
            "Add a new entity (table/collection/node) to the schema. "
            "Provide a PascalCase name, a list of fields, and optionally a storage engine."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entity name in PascalCase (e.g. 'User', 'Product')."},
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Field name in snake_case."},
                            "field_type": {
                                "type": "string",
                                "description": (
                                    "Field type: string, text, integer, float, boolean, "
                                    "datetime, date, uuid, json, array, binary, enum."
                                ),
                            },
                            "primary_key": {"type": "boolean", "description": "Whether this is the primary key."},
                            "nullable": {"type": "boolean", "description": "Whether the field accepts null."},
                            "unique": {"type": "boolean", "description": "Whether values must be unique."},
                            "indexed": {"type": "boolean", "description": "Whether the field is indexed."},
                        },
                        "required": ["name", "field_type"],
                    },
                    "description": "List of field definitions.",
                },
                "storage_engine": {
                    "type": "string",
                    "description": "Storage engine: sql, mongo, graph, vector. Defaults to sql.",
                },
                "description": {"type": "string", "description": "Human-readable entity description."},
            },
            "required": ["name", "fields"],
        },
    },
    {
        "name": "add_relationship",
        "description": "Define a relationship between two entities.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Relationship name."},
                "source_entity": {"type": "string", "description": "Source entity name."},
                "target_entity": {"type": "string", "description": "Target entity name."},
                "relationship_type": {
                    "type": "string",
                    "description": "Type: hard, soft, or graph. Defaults to hard.",
                },
                "cardinality": {
                    "type": "string",
                    "description": "Cardinality: one_to_one, one_to_many, many_to_one, many_to_many.",
                },
                "source_field": {"type": "string", "description": "FK field on source entity."},
                "target_field": {"type": "string", "description": "Referenced field on target entity."},
                "description": {"type": "string", "description": "Relationship description."},
            },
            "required": ["name", "source_entity", "target_entity"],
        },
    },
    {
        "name": "create_domain",
        "description": "Group entities into a logical domain with its own Expert Agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Domain name (e.g. 'Users', 'Inventory')."},
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity names belonging to this domain.",
                },
                "description": {"type": "string", "description": "Domain description."},
            },
            "required": ["name", "entities"],
        },
    },
    {
        "name": "review_schema",
        "description": "Show the current schema summary to the user.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "confirm_schema",
        "description": "Finalize and validate the schema. Returns the full ASD as JSON.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "introspect_database",
        "description": "Connect to a database and discover its schema via introspection.",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_string": {
                    "type": "string",
                    "description": "Database connection URI (e.g. postgresql://user:pass@host/db).",
                },
            },
            "required": ["connection_string"],
        },
    },
]
