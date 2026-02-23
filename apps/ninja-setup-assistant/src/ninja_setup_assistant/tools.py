"""ADK tool definitions that manipulate an in-memory AgenticSchema.

All tools operate on a shared ``SchemaWorkspace`` instance so they can be
tested independently of any LLM.  The ``create_adk_tools`` factory produces
bound wrapper functions suitable for passing to ``LlmAgent(tools=...)``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import (
    MAX_DESCRIPTION_LENGTH,
    EntitySchema,
    FieldSchema,
    FieldType,
    StorageEngine,
)
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType
from ninja_core.security import check_ssrf
from ninja_introspect.engine import IntrospectionEngine

# Allowed relationship types and cardinalities for boundary validation.
_ALLOWED_RELATIONSHIP_TYPES = {rt.value for rt in RelationshipType}
_ALLOWED_CARDINALITIES = {c.value for c in Cardinality}

_ALLOWED_DB_SCHEMES = {
    "postgresql",
    "postgresql+asyncpg",
    "postgresql+aiosqlite",
    "postgres",
    "postgres+asyncpg",
    "mysql",
    "mysql+aiomysql",
    "mysql+asyncmy",
    "sqlite",
    "sqlite+aiosqlite",
    "mongodb",
    "mongodb+srv",
    "neo4j",
    "neo4j+s",
    "neo4j+ssc",
    "bolt",
    "bolt+s",
    "bolt+ssc",
}

# Same regex used in ninja-core schema validators.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

# Allowed field types for validation at the tool boundary.
_ALLOWED_FIELD_TYPES = {ft.value for ft in FieldType}

# Allowed storage engines.
_ALLOWED_STORAGE_ENGINES = {se.value for se in StorageEngine}


def _validate_identifier(value: str, label: str) -> str | None:
    """Validate a name is a safe identifier. Returns error message or None.

    The raw *value* is intentionally omitted from error messages to prevent
    prompt injection via unsanitized user input echoed in LLM tool output.
    """
    if not value or not value.strip():
        return f"{label} must not be empty."
    if not _IDENTIFIER_RE.match(value.strip()):
        return (
            f"{label} is not a valid identifier. "
            "Must start with a letter, contain only alphanumeric characters "
            "and underscores, and be at most 64 characters."
        )
    return None


def _validate_description(value: str | None, label: str) -> str | None:
    """Validate description length. Returns error message or None."""
    if value is not None and len(value) > MAX_DESCRIPTION_LENGTH:
        return f"{label} description too long ({len(value)} chars). Maximum is {MAX_DESCRIPTION_LENGTH} characters."
    return None


def _tool_result(status: str, message: str, **data: Any) -> str:
    """Return a structured JSON tool result.

    Separates instruction text (``message``) from user-provided data so that
    LLM tool output cannot be confused with system instructions, mitigating
    prompt injection via unsanitized values.

    Args:
        status: ``"ok"`` for success, ``"error"`` for failures.
        message: Human-readable description of what happened.
        **data: Arbitrary data fields to include in the response.

    Returns:
        A JSON string with ``status``, ``message``, and any extra data fields.
    """
    payload: dict[str, Any] = {"status": status, "message": message}
    payload.update(data)
    return json.dumps(payload)


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
    # Validate entity name at tool boundary.
    error = _validate_identifier(name, "Entity name")
    if error:
        return _tool_result("error", error)

    # Validate storage engine.
    if storage_engine not in _ALLOWED_STORAGE_ENGINES:
        return _tool_result(
            "error",
            "Invalid storage engine. See allowed_values for valid options.",
            allowed_values=sorted(_ALLOWED_STORAGE_ENGINES),
        )

    # Validate description length.
    error = _validate_description(description, "Entity")
    if error:
        return _tool_result("error", error)

    for existing in workspace.schema.entities:
        if existing.name == name:
            return _tool_result("error", "Entity already exists. Use a different name or remove it first.", entity=name)

    # Validate field names and types.
    for f in fields:
        field_name = f.get("name", "")
        error = _validate_identifier(field_name, "Field name")
        if error:
            return _tool_result("error", error)
        field_type = f.get("field_type", "string")
        if field_type not in _ALLOWED_FIELD_TYPES:
            return _tool_result(
                "error",
                "Invalid field type. See allowed_types for valid options.",
                field=field_name,
                allowed_types=sorted(_ALLOWED_FIELD_TYPES),
            )

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
    field_names = [f.name for f in parsed_fields]
    return _tool_result("ok", "Entity added.", entity=name, storage_engine=storage_engine, fields=field_names)


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
        A structured JSON confirmation or error message.
    """
    # Validate all identifier inputs at the tool boundary.
    for value, label in [
        (name, "Relationship name"),
        (source_entity, "Source entity name"),
        (target_entity, "Target entity name"),
    ]:
        error = _validate_identifier(value, label)
        if error:
            return _tool_result("error", error)

    if source_field is not None:
        error = _validate_identifier(source_field, "Source field name")
        if error:
            return _tool_result("error", error)
    if target_field is not None:
        error = _validate_identifier(target_field, "Target field name")
        if error:
            return _tool_result("error", error)

    # Validate relationship_type and cardinality against allowed enums.
    if relationship_type not in _ALLOWED_RELATIONSHIP_TYPES:
        return _tool_result(
            "error",
            "Invalid relationship type. See allowed_values for valid options.",
            allowed_values=sorted(_ALLOWED_RELATIONSHIP_TYPES),
        )
    if cardinality not in _ALLOWED_CARDINALITIES:
        return _tool_result(
            "error",
            "Invalid cardinality. See allowed_values for valid options.",
            allowed_values=sorted(_ALLOWED_CARDINALITIES),
        )

    # Validate description length.
    error = _validate_description(description, "Relationship")
    if error:
        return _tool_result("error", error)

    entity_names = {e.name for e in workspace.schema.entities}
    if source_entity not in entity_names:
        return _tool_result("error", "Source entity not found. Add it first.", entity=source_entity)
    if target_entity not in entity_names:
        return _tool_result("error", "Target entity not found. Add it first.", entity=target_entity)

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
    return _tool_result(
        "ok",
        "Relationship added.",
        relationship=name,
        source_entity=source_entity,
        target_entity=target_entity,
        cardinality=cardinality,
    )


def create_domain(
    workspace: SchemaWorkspace,
    name: str,
    entities: list[str],
    description: str | None = None,
) -> str:
    """Group entities into a logical domain.

    Returns:
        A structured JSON confirmation or error message.
    """
    # Validate domain name at tool boundary.
    error = _validate_identifier(name, "Domain name")
    if error:
        return _tool_result("error", error)

    # Validate all entity names in the list are safe identifiers.
    for entity_name in entities:
        error = _validate_identifier(entity_name, "Entity name")
        if error:
            return _tool_result("error", error)

    # Validate description length.
    error = _validate_description(description, "Domain")
    if error:
        return _tool_result("error", error)

    entity_names = {e.name for e in workspace.schema.entities}
    missing = [e for e in entities if e not in entity_names]
    if missing:
        return _tool_result("error", "Some entities not found. Add them first.", missing_entities=missing)

    for existing in workspace.schema.domains:
        if existing.name == name:
            return _tool_result("error", "Domain already exists.", domain=name)

    domain = DomainSchema(name=name, entities=entities, description=description)
    workspace.schema.domains.append(domain)
    return _tool_result("ok", "Domain created.", domain=name, entities=entities)


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
        return _tool_result("error", "Cannot confirm: no entities defined yet.")

    return _tool_result("ok", "Schema confirmed.", schema=schema.model_dump())


def _validate_connection_string(
    connection_string: str,
    *,
    allow_private_hosts: bool = False,
) -> str | None:
    """Validate a connection string format. Returns an error message or None.

    Args:
        connection_string: The database connection URI to validate.
        allow_private_hosts: If ``True``, skip SSRF checks for private/internal
            network addresses.  Intended for legitimate local development only.
    """
    parsed = urlparse(connection_string)
    scheme = parsed.scheme
    if not scheme:
        return "Invalid connection string: missing scheme."
    if scheme not in _ALLOWED_DB_SCHEMES:
        return f"Unsupported database scheme. Allowed schemes: {', '.join(sorted(_ALLOWED_DB_SCHEMES))}."
    base_scheme = scheme.split("+")[0]
    if base_scheme == "sqlite":
        db_path = parsed.path
        if not db_path or db_path == "/":
            return "Invalid SQLite URL: missing database path."
        if db_path.startswith("//") and not db_path.startswith("///:memory:"):
            return "Rejected SQLite URL: absolute paths via sqlite:////... are not allowed in this context."
    # SSRF protection — block private/reserved IP ranges
    ssrf_error = check_ssrf(connection_string, allow_private_hosts=allow_private_hosts)
    if ssrf_error:
        return ssrf_error
    return None


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
    error = _validate_connection_string(connection_string)
    if error:
        return _tool_result("error", f"Connection rejected: {error}")

    try:
        engine = IntrospectionEngine(project_name=workspace.schema.project_name)
        result = await engine.run([connection_string])
    except ValueError as exc:
        return _tool_result("error", "Invalid connection string.", detail=str(exc))
    except Exception as exc:
        return _tool_result("error", "Introspection failed.", error_type=type(exc).__name__, detail=str(exc))

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

    return _tool_result(
        "ok", "Introspection complete.", new_entities=new_entities, new_relationships=new_rels
    )


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
    """Coerce a value to bool (handles string 'true'/'false' from LLM).

    Raises:
        ValueError: If *value* is a string not recognised as a boolean.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in ("true", "1", "yes"):
            return True
        if normalized in ("false", "0", "no"):
            return False
        raise ValueError(
            f"Cannot convert {value!r} to bool. Expected one of: "
            "true/false, yes/no, 1/0."
        )
    return bool(value)
