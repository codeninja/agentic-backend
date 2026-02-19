"""Entity and field schema definitions for the Agentic Schema Definition."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
