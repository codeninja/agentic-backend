"""Tests for the MongoDB introspection provider using mocks."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from ninja_core.schema.entity import FieldType, StorageEngine
from ninja_introspect.providers.mongo import MongoProvider, _infer_field_type, _merge_field_info


class TestInferFieldType:
    def test_string(self):
        assert _infer_field_type("hello") == FieldType.STRING

    def test_integer(self):
        assert _infer_field_type(42) == FieldType.INTEGER

    def test_float(self):
        assert _infer_field_type(3.14) == FieldType.FLOAT

    def test_boolean(self):
        assert _infer_field_type(True) == FieldType.BOOLEAN

    def test_datetime(self):
        assert _infer_field_type(datetime.now()) == FieldType.DATETIME

    def test_list(self):
        assert _infer_field_type([1, 2]) == FieldType.ARRAY

    def test_dict(self):
        assert _infer_field_type({"key": "val"}) == FieldType.JSON

    def test_none_defaults_to_string(self):
        assert _infer_field_type(None) == FieldType.STRING


class TestMergeFieldInfo:
    def test_first_doc(self):
        info: dict = {}
        _merge_field_info(info, {"name": "Alice", "age": 30})
        assert "name" in info
        assert "age" in info
        assert info["name"]["type"] == FieldType.STRING
        assert info["age"]["type"] == FieldType.INTEGER

    def test_nullable_tracking(self):
        info: dict = {}
        _merge_field_info(info, {"name": "Alice"})
        _merge_field_info(info, {"name": None})
        assert info["name"]["nullable"] is True

    def test_seen_count(self):
        info: dict = {}
        _merge_field_info(info, {"x": 1})
        _merge_field_info(info, {"x": 2})
        _merge_field_info(info, {"x": 3})
        assert info["x"]["seen"] == 3


def _make_mock_client(db_name: str, collections: dict[str, list[dict]]):
    """Create a mock Motor client with the given collections and documents."""
    client = MagicMock()

    mock_db = MagicMock()
    mock_db.name = db_name

    async def mock_list_collection_names():
        return list(collections.keys())

    mock_db.list_collection_names = mock_list_collection_names

    for coll_name, docs in collections.items():
        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=docs)
        mock_coll.find.return_value.limit.return_value = mock_cursor
        mock_db.__getitem__ = MagicMock(side_effect=lambda name, _c=collections: _make_collection_mock(_c, name))

    def _get_default_db():
        return mock_db

    client.get_default_database.return_value = mock_db
    client.__getitem__ = MagicMock(return_value=mock_db)
    client.close = MagicMock()

    return client


def _make_collection_mock(collections: dict[str, list[dict]], name: str):
    mock_coll = MagicMock()
    docs = collections.get(name, [])
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=docs)
    mock_coll.find.return_value.limit.return_value = mock_cursor
    return mock_coll


@patch("ninja_introspect.providers.mongo.AsyncIOMotorClient")
async def test_introspect_basic(mock_motor_cls):
    collections = {
        "users": [
            {"_id": "abc123", "name": "Alice", "age": 30},
            {"_id": "def456", "name": "Bob", "age": 25},
        ],
    }
    mock_client = _make_mock_client("testdb", collections)
    mock_motor_cls.return_value = mock_client

    provider = MongoProvider(sample_size=10)
    result = await provider.introspect("mongodb://localhost:27017/testdb")

    assert len(result.entities) == 1
    entity = result.entities[0]
    assert entity.name == "Users"
    assert entity.storage_engine == StorageEngine.MONGO
    assert entity.collection_name == "users"

    field_names = {f.name for f in entity.fields}
    assert "_id" in field_names
    assert "name" in field_names
    assert "age" in field_names


@patch("ninja_introspect.providers.mongo.AsyncIOMotorClient")
async def test_introspect_empty_collection(mock_motor_cls):
    collections = {"empty_coll": []}
    mock_client = _make_mock_client("testdb", collections)
    mock_motor_cls.return_value = mock_client

    provider = MongoProvider()
    result = await provider.introspect("mongodb://localhost:27017/testdb")

    # Empty collections should be skipped
    assert len(result.entities) == 0


@patch("ninja_introspect.providers.mongo.AsyncIOMotorClient")
async def test_id_field_is_primary_key(mock_motor_cls):
    collections = {
        "items": [{"_id": "x1", "label": "test"}],
    }
    mock_client = _make_mock_client("testdb", collections)
    mock_motor_cls.return_value = mock_client

    provider = MongoProvider()
    result = await provider.introspect("mongodb://localhost:27017/testdb")

    entity = result.entities[0]
    id_field = next(f for f in entity.fields if f.name == "_id")
    assert id_field.primary_key is True
    assert id_field.unique is True
    assert id_field.indexed is True


@patch("ninja_introspect.providers.mongo.AsyncIOMotorClient")
async def test_filters_system_collections(mock_motor_cls):
    collections = {
        "users": [{"_id": "1", "name": "Alice"}],
        "system.profile": [{"_id": "sys1"}],
    }
    mock_client = _make_mock_client("testdb", collections)
    mock_motor_cls.return_value = mock_client

    provider = MongoProvider()
    result = await provider.introspect("mongodb://localhost:27017/testdb")

    entity_names = {e.name for e in result.entities}
    assert "Users" in entity_names
    assert "SystemProfile" not in entity_names
