"""Tests for Chroma adapter error handling — verifies that raw chromadb exceptions
are caught and re-raised as domain PersistenceError subclasses."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.chroma import ChromaVectorAdapter, _is_duplicate_id_error
from ninja_persistence.exceptions import (
    ConnectionFailedError,
    DuplicateEntityError,
    PersistenceError,
    QueryError,
)


@pytest.fixture
def doc_entity() -> EntitySchema:
    return EntitySchema(
        name="Document",
        storage_engine=StorageEngine.SQL,  # storage_engine is metadata-only here
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="title", field_type=FieldType.STRING),
        ],
    )


def _make_chroma_adapter(doc_entity: EntitySchema, collection_mock: MagicMock) -> ChromaVectorAdapter:
    """Create a ChromaVectorAdapter with a mocked client."""
    client = MagicMock()
    client.get_or_create_collection.return_value = collection_mock
    return ChromaVectorAdapter(entity=doc_entity, client=client)


async def test_create_duplicate_raises_duplicate_entity_error(doc_entity: EntitySchema):
    """Adding a document with existing ID raises DuplicateEntityError."""
    coll = MagicMock()
    coll.add.side_effect = ValueError("ID d1 already exists in the collection")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(DuplicateEntityError) as exc_info:
        await adapter.create({"id": "d1", "document": "hello"})
    assert exc_info.value.entity_name == "Document"
    assert exc_info.value.operation == "create"


async def test_create_generic_error_raises_persistence_error(doc_entity: EntitySchema):
    """Adding with unknown error raises PersistenceError."""
    coll = MagicMock()
    coll.add.side_effect = RuntimeError("oops")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(PersistenceError) as exc_info:
        await adapter.create({"id": "d1", "document": "hello"})
    assert exc_info.value.operation == "create"


async def test_find_by_id_error_raises_query_error(doc_entity: EntitySchema):
    """find_by_id with driver error raises QueryError."""
    coll = MagicMock()
    coll.get.side_effect = RuntimeError("query failed")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(QueryError):
        await adapter.find_by_id("d1")


async def test_find_many_error_raises_query_error(doc_entity: EntitySchema):
    """find_many with driver error raises QueryError."""
    coll = MagicMock()
    coll.get.side_effect = RuntimeError("query failed")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(QueryError):
        await adapter.find_many()


async def test_update_error_raises_persistence_error(doc_entity: EntitySchema):
    """update with driver error raises PersistenceError."""
    coll = MagicMock()
    coll.update.side_effect = RuntimeError("update failed")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(PersistenceError):
        await adapter.update("d1", {"title": "new"})


async def test_delete_error_raises_persistence_error(doc_entity: EntitySchema):
    """delete with driver error raises PersistenceError."""
    coll = MagicMock()
    coll.delete.side_effect = RuntimeError("delete failed")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(PersistenceError):
        await adapter.delete("d1")


async def test_search_semantic_error_raises_query_error(doc_entity: EntitySchema):
    """search_semantic with driver error raises QueryError."""
    coll = MagicMock()
    coll.query.side_effect = RuntimeError("search failed")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(QueryError):
        await adapter.search_semantic("test query")


async def test_upsert_embedding_error_raises_persistence_error(doc_entity: EntitySchema):
    """upsert_embedding with driver error raises PersistenceError."""
    coll = MagicMock()
    coll.update.side_effect = RuntimeError("embed failed")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(PersistenceError):
        await adapter.upsert_embedding("d1", [0.1, 0.2])


async def test_get_collection_failure_raises_connection_error(doc_entity: EntitySchema):
    """Client failure during get_or_create_collection raises ConnectionFailedError."""
    client = MagicMock()
    client.get_or_create_collection.side_effect = RuntimeError("connection refused")
    adapter = ChromaVectorAdapter(entity=doc_entity, client=client)

    with pytest.raises(ConnectionFailedError):
        await adapter.find_by_id("d1")


async def test_error_does_not_leak_details(doc_entity: EntitySchema):
    """Domain exception should not expose raw driver internals."""
    coll = MagicMock()
    coll.add.side_effect = ValueError("ID d1 already exists in collection chroma_internal_data")
    adapter = _make_chroma_adapter(doc_entity, coll)

    with pytest.raises(DuplicateEntityError) as exc_info:
        await adapter.create({"id": "d1", "document": "hello"})
    msg = str(exc_info.value)
    assert "chroma_internal" not in msg


# --- Unit tests for helper function ---


def test_is_duplicate_id_error_value_error():
    assert _is_duplicate_id_error(ValueError("ID x already exists")) is True


def test_is_duplicate_id_error_generic():
    assert _is_duplicate_id_error(RuntimeError("nope")) is False


def test_is_duplicate_id_error_by_type_name():
    class DuplicateIDError(Exception):
        pass

    assert _is_duplicate_id_error(DuplicateIDError("dup")) is True


# --- Tests verifying asyncio.to_thread is used for non-blocking I/O ---


async def test_find_by_id_uses_to_thread(doc_entity: EntitySchema):
    """Verify find_by_id offloads the synchronous coll.get call to a thread."""
    coll = MagicMock()
    coll.get.return_value = {"ids": ["d1"], "metadatas": [{"title": "t"}], "documents": ["doc"]}
    adapter = _make_chroma_adapter(doc_entity, coll)

    with patch("ninja_persistence.adapters.chroma.asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
        result = await adapter.find_by_id("d1")

    assert result == {"id": "d1", "title": "t", "document": "doc"}
    # to_thread should be called for _get_collection and coll.get
    assert mock_to_thread.call_count == 2


async def test_create_uses_to_thread(doc_entity: EntitySchema):
    """Verify create offloads coll.add to a thread."""
    coll = MagicMock()
    adapter = _make_chroma_adapter(doc_entity, coll)

    with patch("ninja_persistence.adapters.chroma.asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
        result = await adapter.create({"id": "d1", "document": "hello"})

    assert result == {"id": "d1", "document": "hello"}
    assert mock_to_thread.call_count == 2  # _get_collection + coll.add


async def test_delete_uses_to_thread(doc_entity: EntitySchema):
    """Verify delete offloads coll.delete to a thread."""
    coll = MagicMock()
    adapter = _make_chroma_adapter(doc_entity, coll)

    with patch("ninja_persistence.adapters.chroma.asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
        result = await adapter.delete("d1")

    assert result is True
    assert mock_to_thread.call_count == 2  # _get_collection + coll.delete


async def test_search_semantic_uses_to_thread(doc_entity: EntitySchema):
    """Verify search_semantic offloads coll.query to a thread."""
    coll = MagicMock()
    coll.query.return_value = {
        "ids": [["d1"]],
        "metadatas": [[{"title": "t"}]],
        "documents": [["doc"]],
        "distances": [[0.1]],
    }
    adapter = _make_chroma_adapter(doc_entity, coll)

    with patch("ninja_persistence.adapters.chroma.asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
        results = await adapter.search_semantic("query")

    assert len(results) == 1
    assert results[0]["_distance"] == 0.1
    assert mock_to_thread.call_count == 2  # _get_collection + coll.query


async def test_no_client_raises_runtime_error(doc_entity: EntitySchema):
    """Adapter with no client raises RuntimeError from _get_collection."""
    adapter = ChromaVectorAdapter(entity=doc_entity, client=None)

    # The RuntimeError propagates through find_by_id's handler as a QueryError
    with pytest.raises(QueryError):
        await adapter.find_by_id("d1")
