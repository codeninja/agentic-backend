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


async def test_search_semantic_raises_not_implemented(sql_adapter: SQLAdapter):
    """SQL adapter without sidecar raises NotImplementedError for semantic search."""
    with pytest.raises(NotImplementedError, match="Semantic search not available for SQL adapter"):
        await sql_adapter.search_semantic("test query")


async def test_upsert_embedding_raises_not_implemented(sql_adapter: SQLAdapter):
    """SQL adapter without sidecar raises NotImplementedError for embedding upsert."""
    with pytest.raises(NotImplementedError, match="Embedding storage not available for SQL adapter"):
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


# ---------------------------------------------------------------------------
# Vector sidecar tests
# ---------------------------------------------------------------------------


class FakeSidecar:
    """Minimal sidecar that records calls for verification."""

    def __init__(self) -> None:
        self.search_calls: list[tuple[str, int]] = []
        self.upsert_calls: list[tuple[str, list[float]]] = []
        self.search_results: list[dict] = []
        self.upsert_should_fail = False

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict]:
        self.search_calls.append((query, limit))
        return self.search_results

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        if self.upsert_should_fail:
            raise RuntimeError("sidecar failure")
        self.upsert_calls.append((id, embedding))


@pytest.fixture
async def sidecar_adapter(user_entity: EntitySchema):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sidecar = FakeSidecar()
    adapter = SQLAdapter(engine=engine, entity=user_entity, vector_sidecar=sidecar)
    await adapter.ensure_table()
    yield adapter, sidecar
    await engine.dispose()


async def test_sidecar_search_semantic(sidecar_adapter):
    adapter, sidecar = sidecar_adapter
    sidecar.search_results = [{"id": "1", "name": "Alice", "_distance": 0.1}]

    results = await adapter.search_semantic("find Alice", limit=5)

    assert len(results) == 1
    assert results[0]["id"] == "1"
    assert sidecar.search_calls == [("find Alice", 5)]


async def test_sidecar_upsert_embedding(sidecar_adapter):
    adapter, sidecar = sidecar_adapter

    await adapter.upsert_embedding("rec-1", [0.1, 0.2, 0.3])

    assert sidecar.upsert_calls == [("rec-1", [0.1, 0.2, 0.3])]


async def test_sidecar_upsert_failure_logs_warning(sidecar_adapter, caplog):
    """Sidecar failure on upsert is logged but does not raise."""
    adapter, sidecar = sidecar_adapter
    sidecar.upsert_should_fail = True

    # Should NOT raise — best-effort consistency
    await adapter.upsert_embedding("rec-1", [0.1, 0.2])

    assert "Sidecar upsert_embedding failed" in caplog.text


async def test_has_vector_support_flags(user_entity: EntitySchema):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # No sidecar, no pgvector
    adapter_bare = SQLAdapter(engine=engine, entity=user_entity)
    assert adapter_bare.has_native_vector is False
    assert adapter_bare.has_vector_support is False

    # With sidecar
    adapter_sidecar = SQLAdapter(engine=engine, entity=user_entity, vector_sidecar=FakeSidecar())
    assert adapter_sidecar.has_native_vector is False
    assert adapter_sidecar.has_vector_support is True

    await engine.dispose()


# ---------------------------------------------------------------------------
# Catch-up re-index tests (sidecar path)
# ---------------------------------------------------------------------------


async def test_reindex_missing_embeddings_via_sidecar(user_entity: EntitySchema):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sidecar = FakeSidecar()
    adapter = SQLAdapter(engine=engine, entity=user_entity, vector_sidecar=sidecar)
    await adapter.ensure_table()

    # Insert some records
    await adapter.create({"id": "1", "name": "Alice", "email": "a@test.com", "age": 30})
    await adapter.create({"id": "2", "name": "Bob", "email": "b@test.com", "age": 25})

    async def fake_embed(text: str) -> list[float]:
        return [float(ord(c)) for c in text[:3]]

    count = await adapter.reindex_missing_embeddings(embed_fn=fake_embed, text_field="name")

    assert count == 2
    assert len(sidecar.upsert_calls) == 2
    await engine.dispose()


async def test_reindex_raises_without_vector_support(sql_adapter: SQLAdapter):
    async def fake_embed(text: str) -> list[float]:
        return [0.0]

    with pytest.raises(NotImplementedError, match="no vector backend configured"):
        await sql_adapter.reindex_missing_embeddings(embed_fn=fake_embed)


# ---------------------------------------------------------------------------
# pgvector detection (unit-level, no real Postgres needed)
# ---------------------------------------------------------------------------


def test_is_postgres_detection():
    from ninja_persistence.adapters.sql import _is_postgres
    from unittest.mock import MagicMock

    pg_engine = MagicMock()
    pg_engine.url = "postgresql+asyncpg://localhost/testdb"
    assert _is_postgres(pg_engine) is True

    sqlite_engine = MagicMock()
    sqlite_engine.url = "sqlite+aiosqlite:///:memory:"
    assert _is_postgres(sqlite_engine) is False

    mysql_engine = MagicMock()
    mysql_engine.url = "mysql+aiomysql://localhost/testdb"
    assert _is_postgres(mysql_engine) is False
