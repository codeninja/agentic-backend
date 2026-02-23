"""Tests for MongoDB adapter error handling — verifies that raw pymongo exceptions
are caught and re-raised as domain PersistenceError subclasses."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.mongo import (
    MongoAdapter,
    _is_connection_error,
    _is_duplicate_key_error,
    _reject_mongo_operators,
)
from ninja_persistence.exceptions import (
    ConnectionFailedError,
    DuplicateEntityError,
    PersistenceError,
    QueryError,
)


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


def _make_mongo_adapter(user_entity: EntitySchema, collection_mock: MagicMock) -> MongoAdapter:
    """Create a MongoAdapter with a mocked database and collection."""
    database = MagicMock()
    database.__getitem__ = MagicMock(return_value=collection_mock)
    return MongoAdapter(entity=user_entity, database=database)


class FakeDuplicateKeyError(Exception):
    """Simulates pymongo.errors.DuplicateKeyError."""

    pass


FakeDuplicateKeyError.__name__ = "DuplicateKeyError"


class FakeConnectionFailure(Exception):
    """Simulates pymongo.errors.ConnectionFailure."""

    pass


FakeConnectionFailure.__name__ = "ConnectionFailure"


async def test_create_duplicate_raises_duplicate_entity_error(user_entity: EntitySchema):
    """Insert with duplicate key raises DuplicateEntityError."""
    coll = MagicMock()
    coll.insert_one = AsyncMock(side_effect=FakeDuplicateKeyError("dup"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(DuplicateEntityError) as exc_info:
        await adapter.create({"_id": "1", "name": "Alice"})
    assert exc_info.value.entity_name == "User"
    assert exc_info.value.operation == "create"


async def test_create_connection_error_raises_connection_failed(user_entity: EntitySchema):
    """Insert with connection failure raises ConnectionFailedError."""
    coll = MagicMock()
    coll.insert_one = AsyncMock(side_effect=FakeConnectionFailure("timeout"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(ConnectionFailedError) as exc_info:
        await adapter.create({"_id": "1", "name": "Alice"})
    assert exc_info.value.operation == "create"


async def test_create_generic_error_raises_persistence_error(user_entity: EntitySchema):
    """Insert with unknown error raises PersistenceError."""
    coll = MagicMock()
    coll.insert_one = AsyncMock(side_effect=RuntimeError("oops"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(PersistenceError) as exc_info:
        await adapter.create({"_id": "1", "name": "Alice"})
    assert exc_info.value.operation == "create"


async def test_find_by_id_connection_error(user_entity: EntitySchema):
    """find_by_id with connection failure raises ConnectionFailedError."""
    coll = MagicMock()
    coll.find_one = AsyncMock(side_effect=FakeConnectionFailure("down"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(ConnectionFailedError):
        await adapter.find_by_id("1")


async def test_find_by_id_generic_error(user_entity: EntitySchema):
    """find_by_id with unknown error raises QueryError."""
    coll = MagicMock()
    coll.find_one = AsyncMock(side_effect=RuntimeError("bad query"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(QueryError):
        await adapter.find_by_id("1")


async def test_update_duplicate_key_raises_duplicate_entity_error(user_entity: EntitySchema):
    """Update with duplicate key raises DuplicateEntityError."""
    coll = MagicMock()
    coll.update_one = AsyncMock(side_effect=FakeDuplicateKeyError("dup"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(DuplicateEntityError):
        await adapter.update("1", {"name": "Bob"})


async def test_delete_connection_error(user_entity: EntitySchema):
    """delete with connection failure raises ConnectionFailedError."""
    coll = MagicMock()
    coll.delete_one = AsyncMock(side_effect=FakeConnectionFailure("down"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(ConnectionFailedError):
        await adapter.delete("1")


async def test_delete_generic_error(user_entity: EntitySchema):
    """delete with unknown error raises PersistenceError."""
    coll = MagicMock()
    coll.delete_one = AsyncMock(side_effect=RuntimeError("oops"))
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(PersistenceError):
        await adapter.delete("1")


async def test_error_does_not_leak_details(user_entity: EntitySchema):
    """Domain exception should not expose raw driver message."""
    coll = MagicMock()
    coll.insert_one = AsyncMock(
        side_effect=FakeDuplicateKeyError("E11000 duplicate key error collection: mydb.users index: _id_")
    )
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(DuplicateEntityError) as exc_info:
        await adapter.create({"_id": "1", "name": "Alice"})
    msg = str(exc_info.value)
    assert "mydb" not in msg
    assert "E11000" not in msg


# --- Unit tests for helper functions ---


def test_is_duplicate_key_error_by_name():
    assert _is_duplicate_key_error(FakeDuplicateKeyError("dup")) is True


def test_is_duplicate_key_error_by_code():
    exc = Exception("write error")
    exc.code = 11000  # type: ignore[attr-defined]
    assert _is_duplicate_key_error(exc) is True


def test_is_duplicate_key_error_false():
    assert _is_duplicate_key_error(RuntimeError("nope")) is False


def test_is_connection_error_true():
    assert _is_connection_error(FakeConnectionFailure("timeout")) is True


def test_is_connection_error_false():
    assert _is_connection_error(RuntimeError("nope")) is False


# --- NoSQL injection prevention tests ---


def test_reject_mongo_operators_top_level():
    """Top-level $-prefixed keys are rejected."""
    with pytest.raises(QueryError, match="\\$gt.*not allowed"):
        _reject_mongo_operators({"$gt": 1}, "TestEntity")


def test_reject_mongo_operators_nested():
    """Nested $-prefixed keys inside filter values are rejected."""
    with pytest.raises(QueryError, match="\\$ne.*not allowed"):
        _reject_mongo_operators({"age": {"$ne": ""}}, "TestEntity")


def test_reject_mongo_operators_deeply_nested():
    """Deeply nested $-prefixed keys are rejected."""
    with pytest.raises(QueryError, match="\\$regex.*not allowed"):
        _reject_mongo_operators({"name": {"nested": {"$regex": ".*"}}}, "TestEntity")


def test_reject_mongo_operators_in_list():
    """$-prefixed keys inside list elements are rejected."""
    with pytest.raises(QueryError, match="\\$where.*not allowed"):
        _reject_mongo_operators({"tags": [{"$where": "1==1"}]}, "TestEntity")


def test_reject_mongo_operators_allows_safe_filters():
    """Plain key-value filters pass validation."""
    _reject_mongo_operators({"name": "Alice", "age": 30}, "TestEntity")


def test_reject_mongo_operators_allows_empty():
    """Empty filter dict passes validation."""
    _reject_mongo_operators({}, "TestEntity")


async def test_find_many_rejects_dollar_operator(user_entity: EntitySchema):
    """find_many raises QueryError when filters contain $-prefixed keys."""
    coll = MagicMock()
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(QueryError, match="not allowed"):
        await adapter.find_many(filters={"$gt": ""})


async def test_find_many_rejects_nested_operator(user_entity: EntitySchema):
    """find_many raises QueryError for nested MongoDB operators."""
    coll = MagicMock()
    adapter = _make_mongo_adapter(user_entity, coll)

    with pytest.raises(QueryError, match="not allowed"):
        await adapter.find_many(filters={"password": {"$ne": ""}})
