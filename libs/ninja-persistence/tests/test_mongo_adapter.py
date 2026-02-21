"""Tests for the MongoDB adapter semantic search / embedding error behavior."""

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.mongo import MongoAdapter


@pytest.fixture
def user_entity() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.MONGO,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
        ],
    )


@pytest.fixture
def mongo_adapter(user_entity: EntitySchema) -> MongoAdapter:
    return MongoAdapter(entity=user_entity)


async def test_search_semantic_raises_not_implemented(mongo_adapter: MongoAdapter):
    """MongoDB adapter raises NotImplementedError for semantic search."""
    with pytest.raises(NotImplementedError, match="Semantic search not available for MongoDB adapter"):
        await mongo_adapter.search_semantic("test query")


async def test_upsert_embedding_raises_not_implemented(mongo_adapter: MongoAdapter):
    """MongoDB adapter raises NotImplementedError for embedding upsert."""
    with pytest.raises(NotImplementedError, match="Embedding storage not available for MongoDB adapter"):
        await mongo_adapter.upsert_embedding("1", [0.1, 0.2, 0.3])
