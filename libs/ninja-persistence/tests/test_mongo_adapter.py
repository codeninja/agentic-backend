"""Tests for the MongoDB adapter semantic search / embedding behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.mongo import MongoAdapter
from ninja_persistence.exceptions import QueryError


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


# ---------------------------------------------------------------------------
# Default (no vector support) — raises NotImplementedError
# ---------------------------------------------------------------------------


async def test_search_semantic_raises_not_implemented(mongo_adapter: MongoAdapter):
    """MongoDB adapter without vector config raises NotImplementedError for semantic search."""
    with pytest.raises(NotImplementedError, match="Semantic search not available for MongoDB adapter"):
        await mongo_adapter.search_semantic("test query")


async def test_upsert_embedding_raises_not_implemented(mongo_adapter: MongoAdapter):
    """MongoDB adapter without vector config raises NotImplementedError for embedding upsert."""
    with pytest.raises(NotImplementedError, match="Embedding storage not available for MongoDB adapter"):
        await mongo_adapter.upsert_embedding("1", [0.1, 0.2, 0.3])


# ---------------------------------------------------------------------------
# Property flags
# ---------------------------------------------------------------------------


def test_has_vector_support_flags_default(user_entity: EntitySchema):
    """Default adapter has no vector support."""
    adapter = MongoAdapter(entity=user_entity)
    assert adapter.has_native_vector is False
    assert adapter.has_vector_support is False


def test_has_vector_support_flags_native(user_entity: EntitySchema):
    """Native mode reports native vector support."""
    adapter = MongoAdapter(entity=user_entity, vector_mode="native")
    assert adapter.has_native_vector is True
    assert adapter.has_vector_support is True


def test_has_vector_support_flags_sidecar(user_entity: EntitySchema):
    """Sidecar mode with sidecar provided reports vector support but not native."""
    sidecar = FakeSidecar()
    adapter = MongoAdapter(entity=user_entity, vector_sidecar=sidecar)
    assert adapter.has_native_vector is False
    assert adapter.has_vector_support is True


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
def sidecar() -> FakeSidecar:
    return FakeSidecar()


@pytest.fixture
def sidecar_adapter(user_entity: EntitySchema, sidecar: FakeSidecar) -> MongoAdapter:
    return MongoAdapter(entity=user_entity, vector_sidecar=sidecar)


async def test_sidecar_search_semantic(sidecar_adapter: MongoAdapter, sidecar: FakeSidecar):
    """Sidecar search_semantic delegates to the sidecar."""
    sidecar.search_results = [{"_id": "1", "name": "Alice", "_distance": 0.1}]

    results = await sidecar_adapter.search_semantic("find Alice", limit=5)

    assert len(results) == 1
    assert results[0]["_id"] == "1"
    assert sidecar.search_calls == [("find Alice", 5)]


async def test_sidecar_upsert_embedding(sidecar_adapter: MongoAdapter, sidecar: FakeSidecar):
    """Sidecar upsert_embedding delegates to the sidecar."""
    await sidecar_adapter.upsert_embedding("rec-1", [0.1, 0.2, 0.3])

    assert sidecar.upsert_calls == [("rec-1", [0.1, 0.2, 0.3])]


async def test_sidecar_upsert_failure_logs_warning(sidecar_adapter: MongoAdapter, sidecar: FakeSidecar, caplog):
    """Sidecar failure on upsert is logged but does not raise."""
    sidecar.upsert_should_fail = True

    # Should NOT raise — best-effort consistency
    await sidecar_adapter.upsert_embedding("rec-1", [0.1, 0.2])

    assert "Sidecar upsert_embedding failed" in caplog.text


# ---------------------------------------------------------------------------
# Atlas Vector Search (native mode) tests
# ---------------------------------------------------------------------------


def _make_native_adapter(user_entity: EntitySchema, database: Any = None) -> MongoAdapter:
    """Helper to create a native-mode adapter with a mock database."""
    if database is None:
        database = MagicMock()
    return MongoAdapter(
        entity=user_entity,
        database=database,
        vector_mode="native",
        vector_index_name="test_vector_index",
    )


async def test_native_upsert_embedding(user_entity: EntitySchema):
    """Native mode stores embedding inline via update_one."""
    mock_coll = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    adapter = _make_native_adapter(user_entity, database=mock_db)
    await adapter.upsert_embedding("doc-1", [0.1, 0.2, 0.3])

    mock_coll.update_one.assert_awaited_once_with(
        {"_id": "doc-1"},
        {"$set": {"_embedding": [0.1, 0.2, 0.3]}},
        upsert=True,
    )


async def test_native_search_semantic_valid_vector(user_entity: EntitySchema):
    """Native mode executes $vectorSearch aggregation pipeline."""
    mock_coll = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    # Mock the async iterator returned by aggregate
    result_docs = [
        {"_id": "1", "name": "Alice", "_score": 0.95},
        {"_id": "2", "name": "Bob", "_score": 0.80},
    ]

    async def mock_aggregate(pipeline):
        for doc in result_docs:
            yield doc

    mock_coll.aggregate = mock_aggregate

    adapter = _make_native_adapter(user_entity, database=mock_db)
    results = await adapter.search_semantic("[0.1, 0.2, 0.3]", limit=5)

    assert len(results) == 2
    assert results[0]["_id"] == "1"
    assert results[1]["_id"] == "2"


async def test_native_search_semantic_invalid_vector(user_entity: EntitySchema):
    """Native mode raises QueryError when query is not a valid embedding vector."""
    adapter = _make_native_adapter(user_entity)

    with pytest.raises(QueryError, match="requires an embedding vector"):
        await adapter.search_semantic("not a vector")


async def test_native_search_semantic_non_list_vector(user_entity: EntitySchema):
    """Native mode raises QueryError when query parses to non-list JSON."""
    adapter = _make_native_adapter(user_entity)

    with pytest.raises(QueryError, match="requires an embedding vector"):
        await adapter.search_semantic('{"key": "value"}')


async def test_native_upsert_embedding_connection_error(user_entity: EntitySchema):
    """Native upsert raises ConnectionFailedError on connection failure."""
    from ninja_persistence.exceptions import ConnectionFailedError

    mock_coll = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    # Create an exception that looks like a connection failure
    exc = type("ConnectionFailure", (Exception,), {})()
    mock_coll.update_one.side_effect = exc

    adapter = _make_native_adapter(user_entity, database=mock_db)
    with pytest.raises(ConnectionFailedError):
        await adapter.upsert_embedding("doc-1", [0.1])


async def test_native_search_semantic_connection_error(user_entity: EntitySchema):
    """Native search raises ConnectionFailedError on connection failure."""
    from ninja_persistence.exceptions import ConnectionFailedError

    mock_coll = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    exc = type("ConnectionFailure", (Exception,), {})()

    async def mock_aggregate(pipeline):
        raise exc
        yield  # noqa: F841 - makes this an async generator

    mock_coll.aggregate = mock_aggregate

    adapter = _make_native_adapter(user_entity, database=mock_db)
    with pytest.raises(ConnectionFailedError):
        await adapter.search_semantic("[0.1, 0.2]", limit=5)


async def test_native_upsert_embedding_generic_error(user_entity: EntitySchema):
    """Native upsert raises PersistenceError on non-connection failure."""
    from ninja_persistence.exceptions import PersistenceError

    mock_coll = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)
    mock_coll.update_one.side_effect = RuntimeError("unexpected")

    adapter = _make_native_adapter(user_entity, database=mock_db)
    with pytest.raises(PersistenceError, match="Failed to upsert embedding"):
        await adapter.upsert_embedding("doc-1", [0.1])


async def test_native_search_semantic_generic_error(user_entity: EntitySchema):
    """Native search raises QueryError on non-connection failure."""
    mock_coll = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    async def mock_aggregate(pipeline):
        raise RuntimeError("unexpected")
        yield  # noqa: F841

    mock_coll.aggregate = mock_aggregate

    adapter = _make_native_adapter(user_entity, database=mock_db)
    with pytest.raises(QueryError, match="Atlas Vector Search query failed"):
        await adapter.search_semantic("[0.1, 0.2]", limit=5)


# ---------------------------------------------------------------------------
# Catch-up re-index tests
# ---------------------------------------------------------------------------


async def test_reindex_raises_without_vector_support(mongo_adapter: MongoAdapter):
    """Reindex raises NotImplementedError without any vector backend."""

    async def fake_embed(text: str) -> list[float]:
        return [0.0]

    with pytest.raises(NotImplementedError, match="no vector backend configured"):
        await mongo_adapter.reindex_missing_embeddings(embed_fn=fake_embed)


async def test_reindex_via_sidecar(user_entity: EntitySchema):
    """Sidecar reindex fetches documents and upserts embeddings."""
    sidecar = FakeSidecar()
    mock_coll = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    adapter = MongoAdapter(entity=user_entity, database=mock_db, vector_sidecar=sidecar)

    # Patch find_many to return fake records
    records = [
        {"_id": "1", "name": "Alice"},
        {"_id": "2", "name": "Bob"},
    ]

    async def patched_find_many(filters=None, limit=100):
        return records

    adapter.find_many = patched_find_many  # type: ignore[assignment]

    async def fake_embed(text: str) -> list[float]:
        return [float(ord(c)) for c in text[:3]]

    count = await adapter.reindex_missing_embeddings(embed_fn=fake_embed, text_field="name")

    assert count == 2
    assert len(sidecar.upsert_calls) == 2


async def test_reindex_native_mode(user_entity: EntitySchema):
    """Native reindex scans for documents missing the embedding field."""
    mock_coll = MagicMock()
    mock_coll.update_one = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    docs_missing_embedding = [
        {"_id": "1", "name": "Alice"},
        {"_id": "2", "name": "Bob"},
    ]

    class FakeCursor:
        def __init__(self, docs):
            self._docs = list(docs)

        def limit(self, n):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._docs:
                raise StopAsyncIteration
            return self._docs.pop(0)

    mock_coll.find.return_value = FakeCursor(docs_missing_embedding)

    adapter = MongoAdapter(entity=user_entity, database=mock_db, vector_mode="native")

    embed_calls: list[str] = []

    async def fake_embed(text: str) -> list[float]:
        embed_calls.append(text)
        return [float(ord(c)) for c in text[:3]]

    count = await adapter.reindex_missing_embeddings(embed_fn=fake_embed, text_field="name")

    assert count == 2
    assert embed_calls == ["Alice", "Bob"]
    assert mock_coll.update_one.await_count == 2


async def test_reindex_native_skips_empty_text(user_entity: EntitySchema):
    """Native reindex skips documents where the text field is empty."""
    mock_coll = MagicMock()
    mock_coll.update_one = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    docs = [
        {"_id": "1", "name": "Alice"},
        {"_id": "2", "name": ""},
        {"_id": "3"},  # missing name field
    ]

    class FakeCursor:
        def __init__(self, docs):
            self._docs = list(docs)

        def limit(self, n):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._docs:
                raise StopAsyncIteration
            return self._docs.pop(0)

    mock_coll.find.return_value = FakeCursor(docs)

    adapter = MongoAdapter(entity=user_entity, database=mock_db, vector_mode="native")

    async def fake_embed(text: str) -> list[float]:
        return [0.1]

    count = await adapter.reindex_missing_embeddings(embed_fn=fake_embed, text_field="name")

    # Only "Alice" should be indexed; empty strings are skipped
    assert count == 1


# ---------------------------------------------------------------------------
# Custom configuration
# ---------------------------------------------------------------------------


def test_custom_embedding_field(user_entity: EntitySchema):
    """Custom embedding field name is accepted."""
    adapter = MongoAdapter(
        entity=user_entity,
        vector_mode="native",
        embedding_field="my_vector",
        vector_index_name="my_index",
    )
    assert adapter.has_native_vector is True
    assert adapter._embedding_field == "my_vector"
    assert adapter._vector_index_name == "my_index"


# Needed for type hints in helper function
from typing import Any  # noqa: E402
