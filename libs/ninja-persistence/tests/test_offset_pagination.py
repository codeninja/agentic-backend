"""Tests for offset parameter support across all adapters."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters import _validate_offset
from ninja_persistence.adapters.chroma import ChromaVectorAdapter
from ninja_persistence.adapters.graph import GraphAdapter
from ninja_persistence.adapters.milvus import MilvusVectorAdapter
from ninja_persistence.adapters.mongo import MongoAdapter
from ninja_persistence.adapters.sql import SQLAdapter
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Unit tests for _validate_offset helper
# ---------------------------------------------------------------------------


class TestValidateOffset:
    def test_zero_is_valid(self):
        assert _validate_offset(0) == 0

    def test_positive_is_valid(self):
        assert _validate_offset(10) == 10
        assert _validate_offset(999) == 999

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="offset must be >= 0"):
            _validate_offset(-1)
        with pytest.raises(ValueError, match="offset must be >= 0"):
            _validate_offset(-100)


# ---------------------------------------------------------------------------
# SQL adapter offset tests
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


async def test_sql_find_many_with_offset(sql_adapter: SQLAdapter):
    for i in range(5):
        await sql_adapter.create({"id": str(i), "name": f"User{i}"})

    result = await sql_adapter.find_many(limit=2, offset=2)
    assert len(result) == 2
    # offset=2 skips first 2 records
    ids = {r["id"] for r in result}
    assert len(ids) == 2


async def test_sql_find_many_offset_beyond_results(sql_adapter: SQLAdapter):
    await sql_adapter.create({"id": "1", "name": "Alice"})
    result = await sql_adapter.find_many(offset=10)
    assert result == []


async def test_sql_find_many_offset_zero_is_default(sql_adapter: SQLAdapter):
    await sql_adapter.create({"id": "1", "name": "Alice"})
    result_default = await sql_adapter.find_many()
    result_zero = await sql_adapter.find_many(offset=0)
    assert result_default == result_zero


async def test_sql_find_many_rejects_negative_offset(sql_adapter: SQLAdapter):
    with pytest.raises(ValueError, match="offset must be >= 0"):
        await sql_adapter.find_many(offset=-1)


# ---------------------------------------------------------------------------
# Mongo adapter offset tests
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


async def test_mongo_find_many_with_offset(mongo_entity: EntitySchema):
    mock_cursor = MagicMock()
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.__aiter__ = lambda self: self
    mock_cursor.__anext__ = AsyncMock(side_effect=StopAsyncIteration)

    mock_coll = MagicMock()
    mock_coll.find.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    adapter = MongoAdapter(entity=mongo_entity, database=mock_db)
    await adapter.find_many(offset=5, limit=10)

    mock_cursor.skip.assert_called_once_with(5)
    mock_cursor.limit.assert_called_once_with(10)


async def test_mongo_find_many_rejects_negative_offset(mongo_entity: EntitySchema):
    mock_db = MagicMock()
    adapter = MongoAdapter(entity=mongo_entity, database=mock_db)
    with pytest.raises(ValueError, match="offset must be >= 0"):
        await adapter.find_many(offset=-1)


# ---------------------------------------------------------------------------
# Chroma adapter offset tests
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


def _make_chroma_adapter(entity: EntitySchema) -> tuple[ChromaVectorAdapter, MagicMock]:
    coll = MagicMock()
    coll.get.return_value = {"ids": [], "metadatas": [], "documents": []}
    client = MagicMock()
    client.get_or_create_collection.return_value = coll
    return ChromaVectorAdapter(entity=entity, client=client), coll


async def test_chroma_find_many_with_offset(chroma_entity: EntitySchema):
    adapter, coll = _make_chroma_adapter(chroma_entity)
    await adapter.find_many(offset=5, limit=10)

    call_kwargs = coll.get.call_args[1]
    assert call_kwargs["offset"] == 5
    assert call_kwargs["limit"] == 10


async def test_chroma_find_many_rejects_negative_offset(chroma_entity: EntitySchema):
    adapter, _ = _make_chroma_adapter(chroma_entity)
    with pytest.raises(ValueError, match="offset must be >= 0"):
        await adapter.find_many(offset=-1)


# ---------------------------------------------------------------------------
# Milvus adapter offset tests
# ---------------------------------------------------------------------------


@pytest.fixture
def milvus_entity() -> EntitySchema:
    return EntitySchema(
        name="Vector",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="document", field_type=FieldType.TEXT),
        ],
    )


async def test_milvus_find_many_with_offset(milvus_entity: EntitySchema):
    mock_client = MagicMock()
    mock_client.has_collection.return_value = True
    mock_client.query.return_value = []

    adapter = MilvusVectorAdapter(entity=milvus_entity, client=mock_client)
    await adapter.find_many(offset=5, limit=10)

    call_kwargs = mock_client.query.call_args[1]
    assert call_kwargs["offset"] == 5
    assert call_kwargs["limit"] == 10


async def test_milvus_find_many_rejects_negative_offset(milvus_entity: EntitySchema):
    mock_client = MagicMock()
    adapter = MilvusVectorAdapter(entity=milvus_entity, client=mock_client)
    with pytest.raises(ValueError, match="offset must be >= 0"):
        await adapter.find_many(offset=-1)


# ---------------------------------------------------------------------------
# Graph adapter offset tests
# ---------------------------------------------------------------------------


def _make_mock_driver() -> MagicMock:
    driver = MagicMock()
    session = AsyncMock()
    result = AsyncMock()
    result.data = AsyncMock(return_value=[])

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    driver.session.return_value = ctx

    session.run = AsyncMock(return_value=result)
    return driver


@pytest.fixture
def graph_entity() -> EntitySchema:
    return EntitySchema(
        name="Person",
        storage_engine=StorageEngine.GRAPH,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
        ],
    )


async def test_graph_find_many_with_offset(graph_entity: EntitySchema):
    driver = _make_mock_driver()
    adapter = GraphAdapter(entity=graph_entity, driver=driver)
    await adapter.find_many(offset=5, limit=10)

    session = driver.session.return_value.__aenter__.return_value
    call_args = session.run.call_args
    query = call_args[0][0]
    params = call_args[0][1]

    assert "SKIP $skip" in query
    assert "LIMIT $limit" in query
    assert params["skip"] == 5
    assert params["limit"] == 10


async def test_graph_find_many_with_offset_and_filters(graph_entity: EntitySchema):
    driver = _make_mock_driver()
    adapter = GraphAdapter(entity=graph_entity, driver=driver)
    await adapter.find_many(filters={"name": "Alice"}, offset=3, limit=5)

    session = driver.session.return_value.__aenter__.return_value
    call_args = session.run.call_args
    query = call_args[0][0]
    params = call_args[0][1]

    assert "WHERE" in query
    assert "SKIP $skip" in query
    assert params["skip"] == 3


async def test_graph_find_many_rejects_negative_offset(graph_entity: EntitySchema):
    driver = _make_mock_driver()
    adapter = GraphAdapter(entity=graph_entity, driver=driver)
    with pytest.raises(ValueError, match="offset must be >= 0"):
        await adapter.find_many(offset=-1)
