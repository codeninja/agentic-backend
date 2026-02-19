"""Vector database introspection provider (Chroma / Milvus)."""

from __future__ import annotations

from typing import Any

import chromadb
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine

from ninja_introspect.providers.base import IntrospectionProvider, IntrospectionResult


def _collection_to_pascal(name: str) -> str:
    """Convert a collection name to PascalCase entity name."""
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_"))


class VectorProvider(IntrospectionProvider):
    """Introspects vector databases (Chroma) — reads collection metadata."""

    async def introspect(self, connection_string: str) -> IntrospectionResult:
        """Introspect a Chroma vector database.

        Args:
            connection_string: For Chroma, this is the persist directory path
                or an HTTP URL like ``http://host:port``.
        """
        client = self._create_client(connection_string)
        collections = client.list_collections()

        entities: list[EntitySchema] = []
        for collection in collections:
            entity = self._introspect_collection(collection)
            entities.append(entity)

        return IntrospectionResult(entities=entities)

    def _create_client(self, connection_string: str) -> Any:
        """Create a Chroma client from a connection string."""
        if connection_string.startswith("http://") or connection_string.startswith("https://"):
            host, _, port = connection_string.split("//", 1)[1].partition(":")
            return chromadb.HttpClient(host=host, port=int(port) if port else 8000)
        # Treat as persist directory for ephemeral / file-based Chroma
        return chromadb.PersistentClient(path=connection_string)

    def _introspect_collection(self, collection: Any) -> EntitySchema:
        """Build an EntitySchema from a Chroma collection."""
        metadata = collection.metadata or {}

        fields: list[FieldSchema] = [
            FieldSchema(
                name="id",
                field_type=FieldType.STRING,
                primary_key=True,
                unique=True,
                indexed=True,
                description="Chroma document ID",
            ),
            FieldSchema(
                name="document",
                field_type=FieldType.TEXT,
                nullable=True,
                description="Raw document text",
            ),
            FieldSchema(
                name="embedding",
                field_type=FieldType.ARRAY,
                nullable=True,
                description="Vector embedding",
            ),
        ]

        # Add metadata fields if we can peek at stored documents
        try:
            peek = collection.peek(limit=1)
            if peek and peek.get("metadatas"):
                sample_meta = peek["metadatas"][0] or {}
                for key, value in sorted(sample_meta.items()):
                    fields.append(
                        FieldSchema(
                            name=f"meta_{key}",
                            field_type=_infer_metadata_type(value),
                            nullable=True,
                            description=f"Metadata field: {key}",
                        )
                    )
        except Exception:
            pass

        return EntitySchema(
            name=_collection_to_pascal(collection.name),
            storage_engine=StorageEngine.VECTOR,
            fields=fields,
            collection_name=collection.name,
            description=metadata.get("description"),
        )


def _infer_metadata_type(value: Any) -> FieldType:
    """Infer FieldType from a Chroma metadata value."""
    if isinstance(value, bool):
        return FieldType.BOOLEAN
    if isinstance(value, int):
        return FieldType.INTEGER
    if isinstance(value, float):
        return FieldType.FLOAT
    return FieldType.STRING
