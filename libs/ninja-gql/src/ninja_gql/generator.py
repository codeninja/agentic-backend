"""ASD-to-Strawberry type/query/mutation generator.

Takes an ``AgenticSchema`` and produces Strawberry ``@strawberry.type`` classes,
Query fields (get / list / search), and Mutation fields (create / update / delete)
at runtime using dynamic class creation.
"""

import datetime
import uuid
from typing import Any

import strawberry
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import Cardinality, RelationshipSchema

# ---------------------------------------------------------------------------
# Field-type mapping
# ---------------------------------------------------------------------------

_FIELD_TYPE_MAP: dict[FieldType, type] = {
    FieldType.STRING: str,
    FieldType.TEXT: str,
    FieldType.INTEGER: int,
    FieldType.FLOAT: float,
    FieldType.BOOLEAN: bool,
    FieldType.DATETIME: datetime.datetime,
    FieldType.DATE: datetime.date,
    FieldType.UUID: uuid.UUID,
    FieldType.JSON: strawberry.scalars.JSON,
    FieldType.ARRAY: list[str],
    FieldType.BINARY: str,
    FieldType.ENUM: str,
}


def _python_type(field: FieldSchema) -> type:
    """Resolve a FieldSchema to a Python/Strawberry-compatible type."""
    base = _FIELD_TYPE_MAP.get(field.field_type, str)
    if field.nullable:
        return base | None  # type: ignore[return-value]
    return base


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class GqlGenerator:
    """Generates Strawberry types, input types, queries, and mutations from an ASD."""

    def __init__(self, schema: AgenticSchema) -> None:
        self.schema = schema
        self._types: dict[str, type] = {}
        self._input_types: dict[str, type] = {}
        self._entity_map: dict[str, EntitySchema] = {e.name: e for e in schema.entities}
        self._rel_by_source: dict[str, list[RelationshipSchema]] = {}
        for rel in schema.relationships:
            self._rel_by_source.setdefault(rel.source_entity, []).append(rel)

    # -- public API ----------------------------------------------------------

    def generate_types(self) -> dict[str, type]:
        """Create a Strawberry ``@strawberry.type`` class per entity.

        Returns a mapping ``{EntityName: StrawberryType}``.
        """
        if self._types:
            return self._types

        # First pass: create basic types (no relationships yet)
        for entity in self.schema.entities:
            self._types[entity.name] = self._make_type(entity)

        # Second pass: wire relationship fields
        for entity in self.schema.entities:
            self._attach_relationships(entity)

        return self._types

    def generate_input_types(self) -> dict[str, tuple[type, type]]:
        """Create Strawberry input types for create and update operations.

        Returns ``{EntityName: (CreateInput, UpdateInput)}``.
        """
        if self._input_types:
            return self._input_types

        for entity in self.schema.entities:
            create_cls, update_cls = self._make_input_types(entity)
            self._input_types[entity.name] = (create_cls, update_cls)
        return self._input_types

    def get_type(self, entity_name: str) -> type:
        """Return the generated Strawberry type for *entity_name*."""
        if not self._types:
            self.generate_types()
        return self._types[entity_name]

    def has_embeddable_fields(self, entity: EntitySchema) -> bool:
        """Return True if the entity has any field with embedding config."""
        return any(f.embedding is not None for f in entity.fields)

    # -- internals -----------------------------------------------------------

    def _make_type(self, entity: EntitySchema) -> type:
        annotations: dict[str, Any] = {}
        namespace: dict[str, Any] = {"__annotations__": annotations}

        for f in entity.fields:
            py_type = _python_type(f)
            annotations[f.name] = py_type
            if f.nullable:
                namespace[f.name] = None

        cls = type(entity.name, (), namespace)
        cls.__annotations__ = annotations
        return strawberry.type(cls, description=entity.description or f"GraphQL type for {entity.name}")

    def _attach_relationships(self, entity: EntitySchema) -> None:
        rels = self._rel_by_source.get(entity.name, [])
        if not rels:
            return

        gql_type = self._types[entity.name]

        for rel in rels:
            target_type = self._types.get(rel.target_entity)
            if target_type is None:
                continue

            if rel.cardinality in (Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_MANY):
                field_type = list[target_type]  # type: ignore[valid-type]
            else:
                field_type = target_type | None  # type: ignore[assignment]

            field_name = rel.name.lower().replace(" ", "_")
            gql_type.__annotations__[field_name] = field_type
            if rel.cardinality in (Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_MANY):
                setattr(gql_type, field_name, strawberry.UNSET)
            else:
                setattr(gql_type, field_name, None)

    def _make_input_types(self, entity: EntitySchema) -> tuple[type, type]:
        create_annotations: dict[str, Any] = {}
        create_ns: dict[str, Any] = {"__annotations__": create_annotations}
        update_annotations: dict[str, Any] = {}
        update_ns: dict[str, Any] = {"__annotations__": update_annotations}

        for f in entity.fields:
            py_type = _python_type(f)
            if f.primary_key:
                # create: optional (auto-generated), update: required to identify
                create_annotations[f.name] = py_type | None  # type: ignore[assignment]
                create_ns[f.name] = None
                update_annotations[f.name] = py_type
            else:
                create_annotations[f.name] = py_type
                if f.nullable:
                    create_ns[f.name] = None
                # update: all fields optional
                update_annotations[f.name] = py_type | None  # type: ignore[assignment]
                update_ns[f.name] = strawberry.UNSET

        create_cls = type(f"Create{entity.name}Input", (), create_ns)
        create_cls.__annotations__ = create_annotations
        update_cls = type(f"Update{entity.name}Input", (), update_ns)
        update_cls.__annotations__ = update_annotations

        return (
            strawberry.input(create_cls, description=f"Input for creating a {entity.name}"),
            strawberry.input(update_cls, description=f"Input for updating a {entity.name}"),
        )
