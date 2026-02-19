"""Tests for the vector database introspection provider using mocks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ninja_core.schema.entity import FieldType, StorageEngine
from ninja_introspect.providers.vector import VectorProvider, _infer_metadata_type


class TestInferMetadataType:
    def test_bool(self):
        assert _infer_metadata_type(True) == FieldType.BOOLEAN

    def test_int(self):
        assert _infer_metadata_type(42) == FieldType.INTEGER

    def test_float(self):
        assert _infer_metadata_type(3.14) == FieldType.FLOAT

    def test_string(self):
        assert _infer_metadata_type("hello") == FieldType.STRING


def _make_mock_collection(name: str, metadata: dict | None = None, peek_metadatas: list[dict] | None = None):
    """Create a mock Chroma collection."""
    coll = MagicMock()
    coll.name = name
    coll.metadata = metadata or {}

    if peek_metadatas is not None:
        coll.peek.return_value = {"metadatas": peek_metadatas}
    else:
        coll.peek.return_value = {"metadatas": []}

    return coll


@patch("ninja_introspect.providers.vector.chromadb")
async def test_introspect_basic(mock_chromadb):
    mock_client = MagicMock()
    mock_chromadb.PersistentClient.return_value = mock_client

    coll = _make_mock_collection("documents")
    mock_client.list_collections.return_value = [coll]

    provider = VectorProvider()
    result = await provider.introspect("/tmp/chroma_data")

    assert len(result.entities) == 1
    entity = result.entities[0]
    assert entity.name == "Documents"
    assert entity.storage_engine == StorageEngine.VECTOR
    assert entity.collection_name == "documents"


@patch("ninja_introspect.providers.vector.chromadb")
async def test_base_fields_present(mock_chromadb):
    mock_client = MagicMock()
    mock_chromadb.PersistentClient.return_value = mock_client

    coll = _make_mock_collection("embeddings")
    mock_client.list_collections.return_value = [coll]

    provider = VectorProvider()
    result = await provider.introspect("/tmp/chroma_data")

    entity = result.entities[0]
    field_names = {f.name for f in entity.fields}
    assert "id" in field_names
    assert "document" in field_names
    assert "embedding" in field_names

    id_field = next(f for f in entity.fields if f.name == "id")
    assert id_field.primary_key is True


@patch("ninja_introspect.providers.vector.chromadb")
async def test_metadata_fields_from_peek(mock_chromadb):
    mock_client = MagicMock()
    mock_chromadb.PersistentClient.return_value = mock_client

    coll = _make_mock_collection(
        "docs",
        peek_metadatas=[{"source": "web", "page": 1, "score": 0.95}],
    )
    mock_client.list_collections.return_value = [coll]

    provider = VectorProvider()
    result = await provider.introspect("/tmp/chroma_data")

    entity = result.entities[0]
    field_names = {f.name for f in entity.fields}
    assert "meta_source" in field_names
    assert "meta_page" in field_names
    assert "meta_score" in field_names

    meta_page = next(f for f in entity.fields if f.name == "meta_page")
    assert meta_page.field_type == FieldType.INTEGER


@patch("ninja_introspect.providers.vector.chromadb")
async def test_http_connection_string(mock_chromadb):
    mock_client = MagicMock()
    mock_chromadb.HttpClient.return_value = mock_client

    coll = _make_mock_collection("test_coll")
    mock_client.list_collections.return_value = [coll]

    provider = VectorProvider()
    result = await provider.introspect("http://localhost:8000")

    mock_chromadb.HttpClient.assert_called_once_with(host="localhost", port=8000)
    assert len(result.entities) == 1


@patch("ninja_introspect.providers.vector.chromadb")
async def test_multiple_collections(mock_chromadb):
    mock_client = MagicMock()
    mock_chromadb.PersistentClient.return_value = mock_client

    colls = [
        _make_mock_collection("articles"),
        _make_mock_collection("faq_entries"),
    ]
    mock_client.list_collections.return_value = colls

    provider = VectorProvider()
    result = await provider.introspect("/tmp/chroma_data")

    assert len(result.entities) == 2
    names = {e.name for e in result.entities}
    assert "Articles" in names
    assert "FaqEntries" in names
