"""Tests for the Milvus vector adapter."""

from unittest.mock import MagicMock

import pytest
from ninja_core.schema.entity import (
    EmbeddingConfig,
    EntitySchema,
    FieldSchema,
    FieldType,
    StorageEngine,
)
from ninja_persistence.adapters.milvus import MilvusVectorAdapter
from ninja_persistence.protocols import Repository


def _make_entity(
    *,
    name: str = "Article",
    collection_name: str | None = None,
    embedding_dim: int | None = None,
) -> EntitySchema:
    fields = [
        FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
        FieldSchema(name="title", field_type=FieldType.STRING),
        FieldSchema(
            name="body",
            field_type=FieldType.TEXT,
            embedding=EmbeddingConfig(model="text-embedding-3-small", dimensions=embedding_dim or 128)
            if embedding_dim is not False  # noqa: E712
            else None,
        ),
    ]
    if embedding_dim is False:
        # Strip embedding config
        fields[2] = FieldSchema(name="body", field_type=FieldType.TEXT)
    return EntitySchema(
        name=name,
        storage_engine=StorageEngine.VECTOR,
        collection_name=collection_name,
        fields=fields,
    )


def _mock_client(existing_data: dict[str, dict] | None = None) -> MagicMock:
    """Build a MagicMock that behaves like pymilvus.MilvusClient.

    ``existing_data`` maps id -> row dict for pre-populated records.
    """
    store: dict[str, dict] = dict(existing_data) if existing_data else {}
    client = MagicMock()
    client.has_collection.return_value = False

    def fake_insert(collection_name: str, data: list[dict]) -> dict:
        for row in data:
            store[row["id"]] = dict(row)
        return {"insert_count": len(data), "ids": [r["id"] for r in data]}

    def fake_upsert(collection_name: str, data: list[dict]) -> dict:
        for row in data:
            store[row["id"]] = dict(row)
        return {"upsert_count": len(data)}

    def fake_get(collection_name: str, ids: list[str], **kwargs) -> list[dict]:
        results = []
        for doc_id in ids:
            if doc_id in store:
                results.append(dict(store[doc_id]))
        return results

    def fake_query(collection_name: str, filter: str = "", limit: int = 100, **kwargs) -> list[dict]:
        return list(store.values())[:limit]

    def fake_delete(collection_name: str, ids: list[str] | None = None, **kwargs) -> dict:
        count = 0
        if ids:
            for doc_id in ids:
                if doc_id in store:
                    del store[doc_id]
                    count += 1
        return {"delete_count": count}

    def fake_search(collection_name: str, data: list[list[float]], limit: int = 10, **kwargs) -> list[list[dict]]:
        hits = []
        for doc_id, row in list(store.items())[:limit]:
            entity = {k: v for k, v in row.items() if k != "id"}
            hits.append({"id": doc_id, "distance": 0.1, "entity": entity})
        return [hits]

    client.insert.side_effect = fake_insert
    client.upsert.side_effect = fake_upsert
    client.get.side_effect = fake_get
    client.query.side_effect = fake_query
    client.delete.side_effect = fake_delete
    client.search.side_effect = fake_search

    # Expose store for assertions
    client._store = store
    return client


@pytest.fixture
def entity() -> EntitySchema:
    return _make_entity()


@pytest.fixture
def client() -> MagicMock:
    return _mock_client()


@pytest.fixture
def adapter(entity: EntitySchema, client: MagicMock) -> MilvusVectorAdapter:
    return MilvusVectorAdapter(entity=entity, client=client)


# ------------------------------------------------------------------
# Protocol conformance
# ------------------------------------------------------------------


def test_milvus_adapter_is_repository(entity: EntitySchema):
    adapter = MilvusVectorAdapter(entity=entity)
    assert isinstance(adapter, Repository)


# ------------------------------------------------------------------
# Constructor / configuration
# ------------------------------------------------------------------


def test_collection_name_defaults_to_entity_name(entity: EntitySchema):
    adapter = MilvusVectorAdapter(entity=entity)
    assert adapter._collection_name == "article"


def test_collection_name_override():
    entity = _make_entity(collection_name="custom_articles")
    adapter = MilvusVectorAdapter(entity=entity)
    assert adapter._collection_name == "custom_articles"


def test_dimension_inferred_from_embedding_config():
    entity = _make_entity(embedding_dim=384)
    adapter = MilvusVectorAdapter(entity=entity)
    assert adapter._dimension == 384


def test_dimension_defaults_when_no_embedding_config():
    entity = _make_entity(embedding_dim=False)
    adapter = MilvusVectorAdapter(entity=entity)
    assert adapter._dimension == 1536


def test_dimension_override():
    entity = _make_entity(embedding_dim=128)
    adapter = MilvusVectorAdapter(entity=entity, dimension=256)
    assert adapter._dimension == 256


def test_requires_client():
    entity = _make_entity()
    adapter = MilvusVectorAdapter(entity=entity)
    with pytest.raises(RuntimeError, match="requires a pymilvus MilvusClient"):
        adapter._require_client()


# ------------------------------------------------------------------
# Collection auto-creation
# ------------------------------------------------------------------


async def test_ensure_collection_creates_when_missing(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter._ensure_collection()
    client.has_collection.assert_called_once_with(adapter._collection_name)
    client.create_collection.assert_called_once()
    kwargs = client.create_collection.call_args
    assert kwargs.kwargs["collection_name"] == "article"
    assert kwargs.kwargs["dimension"] == 128
    assert kwargs.kwargs["id_type"] == "string"


async def test_ensure_collection_skips_when_exists(entity: EntitySchema, client: MagicMock):
    client.has_collection.return_value = True
    adapter = MilvusVectorAdapter(entity=entity, client=client)
    await adapter._ensure_collection()
    client.create_collection.assert_not_called()


async def test_ensure_collection_called_once(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter._ensure_collection()
    await adapter._ensure_collection()
    # has_collection should only be checked once due to _collection_ready flag
    client.has_collection.assert_called_once()


# ------------------------------------------------------------------
# CRUD operations
# ------------------------------------------------------------------


async def test_create(adapter: MilvusVectorAdapter, client: MagicMock):
    data = {"id": "1", "document": "Hello world", "title": "Greeting"}
    result = await adapter.create(data)
    assert result == data
    client.insert.assert_called_once()
    inserted = client.insert.call_args.kwargs["data"][0]
    assert inserted["id"] == "1"
    assert inserted["document"] == "Hello world"
    assert inserted["title"] == "Greeting"
    # Zero-vector placeholder since no embedding provided
    assert inserted["embedding"] == [0.0] * 128


async def test_create_with_embedding(adapter: MilvusVectorAdapter, client: MagicMock):
    embedding = [0.5] * 128
    data = {"id": "2", "document": "Test", "embedding": embedding}
    await adapter.create(data)
    inserted = client.insert.call_args.kwargs["data"][0]
    assert inserted["embedding"] == embedding


async def test_find_by_id(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "Test doc", "title": "T1"})
    result = await adapter.find_by_id("1")
    assert result is not None
    assert result["id"] == "1"
    assert result["document"] == "Test doc"


async def test_find_by_id_not_found(adapter: MilvusVectorAdapter, client: MagicMock):
    result = await adapter.find_by_id("nonexistent")
    assert result is None


async def test_find_many(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "Doc A"})
    await adapter.create({"id": "2", "document": "Doc B"})
    results = await adapter.find_many()
    assert len(results) == 2


async def test_find_many_with_limit(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "A"})
    await adapter.create({"id": "2", "document": "B"})
    results = await adapter.find_many(limit=1)
    assert len(results) == 1


async def test_find_many_with_filter(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "A"})
    results = await adapter.find_many(filters={"filter": "title == 'A'"})
    assert isinstance(results, list)
    # Verify the filter was forwarded
    call_kwargs = client.query.call_args.kwargs
    assert call_kwargs["filter"] == "title == 'A'"


async def test_find_many_with_where_compat(adapter: MilvusVectorAdapter, client: MagicMock):
    """The 'where' key is accepted for Chroma compatibility."""
    await adapter.create({"id": "1", "document": "A"})
    await adapter.find_many(filters={"where": "title == 'B'"})
    call_kwargs = client.query.call_args.kwargs
    assert call_kwargs["filter"] == "title == 'B'"


async def test_update(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "Original", "title": "V1"})
    result = await adapter.update("1", {"title": "V2"})
    assert result is not None
    assert result["title"] == "V2"
    # Verify upsert was called
    client.upsert.assert_called()


async def test_update_not_found(adapter: MilvusVectorAdapter, client: MagicMock):
    result = await adapter.update("nonexistent", {"title": "Ghost"})
    assert result is None
    client.upsert.assert_not_called()


async def test_delete(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "Test"})
    result = await adapter.delete("1")
    assert result is True
    client.delete.assert_called_once()


# ------------------------------------------------------------------
# Semantic search
# ------------------------------------------------------------------


async def test_search_semantic_with_embedding(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "ML basics", "embedding": [0.1] * 128})
    query_vec = [0.2] * 128
    results = await adapter.search_semantic("machine learning", query_embedding=query_vec)
    assert len(results) >= 1
    assert results[0]["id"] == "1"
    assert "_distance" in results[0]


async def test_search_semantic_without_embedding_returns_empty(adapter: MilvusVectorAdapter):
    """When no query_embedding is provided, returns empty (text not embedded by Milvus)."""
    results = await adapter.search_semantic("some query")
    assert results == []


# ------------------------------------------------------------------
# Upsert embedding
# ------------------------------------------------------------------


async def test_upsert_embedding_existing_record(adapter: MilvusVectorAdapter, client: MagicMock):
    await adapter.create({"id": "1", "document": "Test", "title": "Original"})
    new_embedding = [0.9] * 128
    await adapter.upsert_embedding("1", new_embedding)
    client.upsert.assert_called()
    upserted = client.upsert.call_args.kwargs["data"][0]
    assert upserted["embedding"] == new_embedding
    # Existing fields should be preserved
    assert upserted["id"] == "1"


async def test_upsert_embedding_new_record(adapter: MilvusVectorAdapter, client: MagicMock):
    new_embedding = [0.5] * 128
    await adapter.upsert_embedding("new-id", new_embedding)
    client.upsert.assert_called()
    upserted = client.upsert.call_args.kwargs["data"][0]
    assert upserted["id"] == "new-id"
    assert upserted["embedding"] == new_embedding
    assert upserted["document"] == ""


# ------------------------------------------------------------------
# Row normalization
# ------------------------------------------------------------------


def test_row_to_dict_strips_dollar_keys():
    row = {"id": "1", "document": "test", "$meta": {"index_name": "x"}}
    result = MilvusVectorAdapter._row_to_dict(row)
    assert "$meta" not in result
    assert result["id"] == "1"
