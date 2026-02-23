"""Tests for limit parameter validation across all adapters."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters import MAX_QUERY_LIMIT, _validate_limit
from ninja_persistence.adapters.chroma import ChromaVectorAdapter
from ninja_persistence.adapters.mongo import MongoAdapter
from ninja_persistence.adapters.sql import SQLAdapter
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Unit tests for the shared _validate_limit helper
# ---------------------------------------------------------------------------


class TestValidateLimit:
    def test_valid_limit(self):
        assert _validate_limit(1) == 1
        assert _validate_limit(50) == 50
        assert _validate_limit(1000) == 1000

    def test_caps_at_max(self):
        assert _validate_limit(1001) == MAX_QUERY_LIMIT
        assert _validate_limit(999_999) == MAX_QUERY_LIMIT

    def test_rejects_zero(self):
        with pytest.raises(ValueError, match="limit must be >= 1"):
            _validate_limit(0)

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="limit must be >= 1"):
            _validate_limit(-1)
        with pytest.raises(ValueError, match="limit must be >= 1"):
            _validate_limit(-100)


# ---------------------------------------------------------------------------
# SQL adapter limit validation
# ---------------------------------------------------------------------------


@pytest.fixture
def user_entity() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
        ],
    )


@pytest.fixture
async def sql_adapter(user_entity: EntitySchema):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    adapter = SQLAdapter(engine=engine, entity=user_entity)
    await adapter.ensure_table()
    yield adapter
    await engine.dispose()


async def test_sql_find_many_rejects_zero(sql_adapter: SQLAdapter):
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await sql_adapter.find_many(limit=0)


async def test_sql_find_many_rejects_negative(sql_adapter: SQLAdapter):
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await sql_adapter.find_many(limit=-5)


async def test_sql_find_many_caps_large_limit(sql_adapter: SQLAdapter):
    await sql_adapter.create({"id": "1", "name": "Alice"})
    result = await sql_adapter.find_many(limit=5000)
    assert len(result) == 1  # only 1 record exists; no error from large limit


async def test_sql_search_semantic_rejects_zero(sql_adapter: SQLAdapter):
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await sql_adapter.search_semantic("query", limit=0)


async def test_sql_search_semantic_rejects_negative(sql_adapter: SQLAdapter):
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await sql_adapter.search_semantic("query", limit=-1)


# ---------------------------------------------------------------------------
# Mongo adapter limit validation
# ---------------------------------------------------------------------------


@pytest.fixture
def mongo_entity() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.MONGO,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
        ],
    )


async def test_mongo_find_many_rejects_zero(mongo_entity: EntitySchema):
    mock_db = MagicMock()
    adapter = MongoAdapter(entity=mongo_entity, database=mock_db)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.find_many(limit=0)


async def test_mongo_find_many_rejects_negative(mongo_entity: EntitySchema):
    mock_db = MagicMock()
    adapter = MongoAdapter(entity=mongo_entity, database=mock_db)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.find_many(limit=-10)


async def test_mongo_search_semantic_rejects_zero(mongo_entity: EntitySchema):
    adapter = MongoAdapter(entity=mongo_entity)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.search_semantic("query", limit=0)


async def test_mongo_search_semantic_rejects_negative(mongo_entity: EntitySchema):
    adapter = MongoAdapter(entity=mongo_entity)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.search_semantic("query", limit=-1)


# ---------------------------------------------------------------------------
# Chroma adapter limit validation
# ---------------------------------------------------------------------------


@pytest.fixture
def chroma_entity() -> EntitySchema:
    return EntitySchema(
        name="Document",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="title", field_type=FieldType.STRING),
        ],
    )


def _make_chroma_adapter(entity: EntitySchema) -> ChromaVectorAdapter:
    coll = MagicMock()
    coll.get.return_value = {"ids": [], "metadatas": [], "documents": []}
    coll.query.return_value = {"ids": [[]], "metadatas": [[]], "documents": [[]], "distances": [[]]}
    client = MagicMock()
    client.get_or_create_collection.return_value = coll
    return ChromaVectorAdapter(entity=entity, client=client)


async def test_chroma_find_many_rejects_zero(chroma_entity: EntitySchema):
    adapter = _make_chroma_adapter(chroma_entity)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.find_many(limit=0)


async def test_chroma_find_many_rejects_negative(chroma_entity: EntitySchema):
    adapter = _make_chroma_adapter(chroma_entity)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.find_many(limit=-1)


async def test_chroma_search_semantic_rejects_zero(chroma_entity: EntitySchema):
    adapter = _make_chroma_adapter(chroma_entity)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.search_semantic("query", limit=0)


async def test_chroma_search_semantic_rejects_negative(chroma_entity: EntitySchema):
    adapter = _make_chroma_adapter(chroma_entity)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await adapter.search_semantic("query", limit=-1)


async def test_chroma_find_many_caps_large_limit(chroma_entity: EntitySchema):
    adapter = _make_chroma_adapter(chroma_entity)
    result = await adapter.find_many(limit=5000)
    assert isinstance(result, list)  # no error; limit silently capped


async def test_chroma_search_semantic_caps_large_limit(chroma_entity: EntitySchema):
    adapter = _make_chroma_adapter(chroma_entity)
    result = await adapter.search_semantic("query", limit=5000)
    assert isinstance(result, list)  # no error; limit silently capped
