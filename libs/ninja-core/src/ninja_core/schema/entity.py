"""Entity and field schema definitions for the Agentic Schema Definition."""

from __future__ import annotations

import keyword
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# Valid identifier: starts with letter, alphanumeric + underscores, max 64 chars.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

# Maximum allowed length for description fields.
MAX_DESCRIPTION_LENGTH = 500


class StorageEngine(str, Enum):
    """Database engine that owns an entity."""

    SQL = "sql"
    MONGO = "mongo"
    GRAPH = "graph"
    VECTOR = "vector"


class FieldType(str, Enum):
    """Supported field types across all storage engines."""

    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    UUID = "uuid"
    JSON = "json"
    ARRAY = "array"
    BINARY = "binary"
    ENUM = "enum"


class EmbeddingConfig(BaseModel):
    """Configuration for vectorizing a field."""

    model: str = Field(description="Embedding model identifier (e.g. 'text-embedding-3-small').")
    dimensions: int = Field(gt=0, description="Vector dimensionality.")
    chunk_strategy: str | None = Field(default=None, description="Chunking strategy for long text fields.")

    model_config = {"extra": "forbid"}


class FieldConstraint(BaseModel):
    """Validation constraints for a field."""

    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1)
    pattern: str | None = Field(default=None, description="Regex pattern for string validation.")
    ge: float | None = Field(default=None, description="Greater than or equal.")
    le: float | None = Field(default=None, description="Less than or equal.")
    enum_values: list[str] | None = Field(default=None, description="Allowed values for enum-type fields.")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_constraint_coherence(self) -> FieldConstraint:
        """Ensure min/max constraints are logically consistent."""
        if self.min_length is not None and self.max_length is not None:
            if self.min_length > self.max_length:
                raise ValueError(
                    f"min_length ({self.min_length}) cannot exceed "
                    f"max_length ({self.max_length})"
                )
        if self.ge is not None and self.le is not None:
            if self.ge > self.le:
                raise ValueError(
                    f"ge ({self.ge}) cannot exceed le ({self.le})"
                )
        return self


# Pydantic BaseModel attributes that must not be used as field names.
# Using these as field names generates syntactically valid Python but causes
# runtime bugs (shadowing Pydantic internals).
_PYDANTIC_RESERVED_ATTRS: frozenset[str] = frozenset({
    "model_config",
    "model_fields",
    "model_computed_fields",
    "model_extra",
    "model_fields_set",
    "model_construct",
    "model_copy",
    "model_dump",
    "model_dump_json",
    "model_json_schema",
    "model_parametrized_name",
    "model_post_init",
    "model_rebuild",
    "model_validate",
    "model_validate_json",
    "model_validate_strings",
})


_FIELD_TYPE_COMPATIBLE_PYTHON_TYPES: dict[FieldType, tuple[type, ...]] = {
    FieldType.STRING: (str,),
    FieldType.TEXT: (str,),
    FieldType.INTEGER: (int,),
    FieldType.FLOAT: (int, float),
    FieldType.BOOLEAN: (bool,),
    FieldType.UUID: (str,),
    FieldType.ENUM: (str,),
}


class FieldSchema(BaseModel):
    """Schema definition for a single field within an entity."""

    name: str = Field(min_length=1, description="Field name.")
    field_type: FieldType = Field(description="Data type of the field.")
    nullable: bool = Field(default=False, description="Whether the field accepts null values.")
    default: Any = Field(default=None, description="Default value for the field.")
    primary_key: bool = Field(default=False, description="Whether this field is the primary key.")
    unique: bool = Field(default=False, description="Whether values must be unique.")
    indexed: bool = Field(default=False, description="Whether the field should be indexed.")
    constraints: FieldConstraint | None = Field(default=None, description="Validation constraints.")
    embedding: EmbeddingConfig | None = Field(
        default=None, description="Embedding config if this field should be vectorized."
    )
    description: str | None = Field(default=None, description="Human-readable description.")

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        """Enforce safe identifier pattern on field names."""
        if not _IDENTIFIER_RE.match(v):
            raise ValueError(
                f"Field name {v!r} is not a valid identifier. "
                "Must start with a letter, contain only alphanumeric characters "
                "and underscores, and be at most 64 characters."
            )
        if keyword.iskeyword(v):
            raise ValueError(f"Field name {v!r} is a Python reserved keyword.")
        if v in _PYDANTIC_RESERVED_ATTRS:
            raise ValueError(
                f"Field name {v!r} is a Pydantic reserved attribute and would "
                "shadow BaseModel internals in generated code."
            )
        return v

    @field_validator("description")
    @classmethod
    def validate_field_description(cls, v: str | None) -> str | None:
        """Enforce maximum length on description."""
        if v is not None and len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"Description too long ({len(v)} chars). "
                f"Maximum is {MAX_DESCRIPTION_LENGTH} characters."
            )
        return v

    @model_validator(mode="after")
    def validate_field_coherence(self) -> FieldSchema:
        """Validate default type compatibility and enum constraints."""
        # Primary key must not be nullable
        if self.primary_key and self.nullable:
            raise ValueError(
                f"Primary key field '{self.name}' must not be nullable"
            )

        # Enum field requires enum_values in constraints
        if self.field_type == FieldType.ENUM:
            if (
                self.constraints is None
                or self.constraints.enum_values is None
                or len(self.constraints.enum_values) == 0
            ):
                raise ValueError(
                    f"Field '{self.name}' with field_type=ENUM requires "
                    f"non-empty constraints.enum_values"
                )

        # Default value type checking (skip None defaults)
        if self.default is not None:
            allowed = _FIELD_TYPE_COMPATIBLE_PYTHON_TYPES.get(self.field_type)
            if allowed is not None and not isinstance(self.default, allowed):
                raise ValueError(
                    f"Field '{self.name}': default value {self.default!r} "
                    f"is not compatible with field_type={self.field_type.value}"
                )
        return self


class EntitySchema(BaseModel):
    """Schema definition for an entity (table, collection, node, or vector store)."""

    name: str = Field(min_length=1, description="Entity name (PascalCase recommended).")
    storage_engine: StorageEngine = Field(description="Database engine that owns this entity.")
    fields: list[FieldSchema] = Field(min_length=1, description="Fields belonging to this entity.")
    collection_name: str | None = Field(
        default=None,
        description="Override for the storage collection/table name. Defaults to entity name.",
    )
    description: str | None = Field(default=None, description="Human-readable description.")
    tags: list[str] = Field(default_factory=list, description="Arbitrary tags for categorization.")

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_entity_name(cls, v: str) -> str:
        """Enforce safe identifier pattern on entity names.

        Rejects names with newlines, quotes, control characters, and Python
        reserved keywords. This is the primary defense against prompt injection
        via schema metadata.
        """
        if not _IDENTIFIER_RE.match(v):
            raise ValueError(
                f"Entity name {v!r} is not a valid identifier. "
                "Must start with a letter, contain only alphanumeric characters "
                "and underscores, and be at most 64 characters."
            )
        if keyword.iskeyword(v):
            raise ValueError(f"Entity name {v!r} is a Python reserved keyword.")
        return v

    @field_validator("description")
    @classmethod
    def validate_entity_description(cls, v: str | None) -> str | None:
        """Enforce maximum length on description."""
        if v is not None and len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"Description too long ({len(v)} chars). "
                f"Maximum is {MAX_DESCRIPTION_LENGTH} characters."
            )
        return v

    @model_validator(mode="after")
    def validate_entity_integrity(self) -> EntitySchema:
        """Validate unique field names and exactly one primary key."""
        # Unique field names
        seen: set[str] = set()
        for f in self.fields:
            if f.name in seen:
                raise ValueError(
                    f"Entity '{self.name}' has duplicate field name '{f.name}'"
                )
            seen.add(f.name)

        # Exactly one primary key
        pk_fields = [f for f in self.fields if f.primary_key]
        if len(pk_fields) == 0:
            raise ValueError(
                f"Entity '{self.name}' must have exactly one primary key field"
            )
        if len(pk_fields) > 1:
            pk_names = [f.name for f in pk_fields]
            raise ValueError(
                f"Entity '{self.name}' has multiple primary key fields: "
                f"{pk_names}"
            )
        return self
