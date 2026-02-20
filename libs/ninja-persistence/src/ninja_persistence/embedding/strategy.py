"""Embedding generation strategy — determines which fields to embed and how."""

from __future__ import annotations

from typing import Any

from ninja_core.schema.entity import EntitySchema, FieldSchema
from pydantic import BaseModel, Field


class EmbeddingStrategy(BaseModel):
    """Configuration for how to generate embeddings for an entity.

    Examines the entity schema to determine which fields have embedding
    configs and produces the text payload to send to the embedding model.
    """

    model_name: str = Field(default="text-embedding-3-small", description="Default embedding model.")
    dimensions: int = Field(default=1536, description="Default vector dimensionality.")
    separator: str = Field(default=" ", description="Separator when concatenating multiple fields.")

    def get_embeddable_fields(self, entity: EntitySchema) -> list[FieldSchema]:
        """Return all fields in the entity that have embedding configuration."""
        return [f for f in entity.fields if f.embedding is not None]

    def build_text_for_embedding(self, entity: EntitySchema, record: dict[str, Any]) -> str:
        """Build the text payload to embed from a record's embeddable fields.

        If no fields have explicit embedding config, falls back to
        concatenating all string/text fields.
        """
        embeddable = self.get_embeddable_fields(entity)
        if embeddable:
            parts = [str(record.get(f.name, "")) for f in embeddable if record.get(f.name)]
            return self.separator.join(parts)

        # Fallback: concatenate all string-like fields
        from ninja_core.schema.entity import FieldType

        text_types = {FieldType.STRING, FieldType.TEXT}
        parts = [
            str(record.get(f.name, "")) for f in entity.fields if f.field_type in text_types and record.get(f.name)
        ]
        return self.separator.join(parts)

    def get_model_for_field(self, field: FieldSchema) -> str:
        """Return the embedding model to use for a specific field."""
        if field.embedding:
            return field.embedding.model
        return self.model_name

    def get_dimensions_for_field(self, field: FieldSchema) -> int:
        """Return the vector dimensions to use for a specific field."""
        if field.embedding:
            return field.embedding.dimensions
        return self.dimensions
