"""Tests for the SQL adapter using async SQLite."""

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.sql import SQLAdapter
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
def user_entity() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="email", field_type=FieldType.STRING, unique=True),
            FieldSchema(name="age", field_type=FieldType.INTEGER, nullable=True),
        ],
    )


@pytest.fixture
async def sql_adapter(user_entity: EntitySchema):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    adapter = SQLAdapter(engine=engine, entity=user_entity)
    await adapter.ensure_table()
    yield adapter
    await engine.dispose()


async def test_create_and_find_by_id(sql_adapter: SQLAdapter):
    data = {"id": "1", "name": "Alice", "email": "alice@example.com", "age": 30}
    result = await sql_adapter.create(data)
    assert result == data

    found = await sql_adapter.find_by_id("1")
    assert found is not None
    assert found["name"] == "Alice"
    assert found["email"] == "alice@example.com"


async def test_find_by_id_not_found(sql_adapter: SQLAdapter):
    result = await sql_adapter.find_by_id("nonexistent")
    assert result is None


async def test_find_many(sql_adapter: SQLAdapter):
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com", "age": 30})
    await sql_adapter.create({"id": "2", "name": "Bob", "email": "b@test.com", "age": 25})
    await sql_adapter.create({"id": "3", "name": "Charlie", "email": "c@test.com", "age": 30})

    all_users = await sql_adapter.find_many()
    assert len(all_users) == 3

    filtered = await sql_adapter.find_many(filters={"age": 30})
    assert len(filtered) == 2


async def test_find_many_with_limit(sql_adapter: SQLAdapter):
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com", "age": 30})
    await sql_adapter.create({"id": "2", "name": "Bob", "email": "b@test.com", "age": 25})

    result = await sql_adapter.find_many(limit=1)
    assert len(result) == 1


async def test_update(sql_adapter: SQLAdapter):
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com", "age": 30})

    updated = await sql_adapter.update("1", {"name": "Alice Updated", "age": 31})
    assert updated is not None
    assert updated["name"] == "Alice Updated"
    assert updated["age"] == 31


async def test_update_not_found(sql_adapter: SQLAdapter):
    result = await sql_adapter.update("nonexistent", {"name": "Ghost"})
    assert result is None


async def test_delete(sql_adapter: SQLAdapter):
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com", "age": 30})

    deleted = await sql_adapter.delete("1")
    assert deleted is True

    found = await sql_adapter.find_by_id("1")
    assert found is None


async def test_delete_not_found(sql_adapter: SQLAdapter):
    result = await sql_adapter.delete("nonexistent")
    assert result is False


async def test_search_semantic_returns_empty(sql_adapter: SQLAdapter):
    """SQL adapter returns empty for semantic search (needs sidecar vector index)."""
    result = await sql_adapter.search_semantic("test query")
    assert result == []


async def test_upsert_embedding_is_noop(sql_adapter: SQLAdapter):
    """SQL adapter embedding upsert is a no-op (needs sidecar vector adapter)."""
    await sql_adapter.upsert_embedding("1", [0.1, 0.2, 0.3])


async def test_custom_table_name():
    entity = EntitySchema(
        name="Product",
        storage_engine=StorageEngine.SQL,
        collection_name="products_v2",
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="title", field_type=FieldType.STRING),
        ],
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    adapter = SQLAdapter(engine=engine, entity=entity)
    assert adapter.table.name == "products_v2"
    await adapter.ensure_table()

    await adapter.create({"id": "p1", "title": "Widget"})
    found = await adapter.find_by_id("p1")
    assert found is not None
    assert found["title"] == "Widget"
    await engine.dispose()
