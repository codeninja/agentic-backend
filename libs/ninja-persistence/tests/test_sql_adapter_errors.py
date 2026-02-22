"""Tests for SQL adapter error handling — verifies that raw SQLAlchemy exceptions
are caught and re-raised as domain PersistenceError subclasses."""

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.sql import SQLAdapter
from ninja_persistence.exceptions import DuplicateEntityError, PersistenceError
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
        ],
    )


@pytest.fixture
async def sql_adapter(user_entity: EntitySchema):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    adapter = SQLAdapter(engine=engine, entity=user_entity)
    await adapter.ensure_table()
    yield adapter
    await engine.dispose()


async def test_create_duplicate_primary_key_raises_duplicate_entity_error(sql_adapter: SQLAdapter):
    """Inserting a record with an existing PK raises DuplicateEntityError."""
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com"})
    with pytest.raises(DuplicateEntityError) as exc_info:
        await sql_adapter.create({"id": "1", "name": "Bob", "email": "b@test.com"})
    assert exc_info.value.entity_name == "User"
    assert exc_info.value.operation == "create"
    assert exc_info.value.__cause__ is not None


async def test_create_duplicate_unique_column_raises_duplicate_entity_error(sql_adapter: SQLAdapter):
    """Inserting a record violating a unique constraint raises DuplicateEntityError."""
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "same@test.com"})
    with pytest.raises(DuplicateEntityError) as exc_info:
        await sql_adapter.create({"id": "2", "name": "Bob", "email": "same@test.com"})
    assert exc_info.value.entity_name == "User"
    assert exc_info.value.operation == "create"


async def test_update_unique_violation_raises_duplicate_entity_error(sql_adapter: SQLAdapter):
    """Updating a record to violate a unique constraint raises DuplicateEntityError."""
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com"})
    await sql_adapter.create({"id": "2", "name": "Bob", "email": "b@test.com"})
    with pytest.raises(DuplicateEntityError) as exc_info:
        await sql_adapter.update("2", {"email": "a@test.com"})
    assert exc_info.value.operation == "update"


async def test_create_uses_engine_begin_transaction(sql_adapter: SQLAdapter):
    """Successful create should work with engine.begin() transaction scoping."""
    result = await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com"})
    assert result["id"] == "1"
    found = await sql_adapter.find_by_id("1")
    assert found is not None
    assert found["name"] == "Alice"


async def test_update_uses_engine_begin_transaction(sql_adapter: SQLAdapter):
    """Successful update should work with engine.begin() transaction scoping."""
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com"})
    updated = await sql_adapter.update("1", {"name": "Alice Updated"})
    assert updated is not None
    assert updated["name"] == "Alice Updated"


async def test_delete_uses_engine_begin_transaction(sql_adapter: SQLAdapter):
    """Successful delete should work with engine.begin() transaction scoping."""
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com"})
    deleted = await sql_adapter.delete("1")
    assert deleted is True
    assert await sql_adapter.find_by_id("1") is None


async def test_all_persistence_errors_are_subclass():
    """All custom exceptions should be catchable as PersistenceError."""
    with pytest.raises(PersistenceError):
        raise DuplicateEntityError(entity_name="X", operation="create", detail="test")


async def test_error_does_not_leak_connection_details(sql_adapter: SQLAdapter):
    """Domain exception messages should not contain raw connection strings."""
    await sql_adapter.create({"id": "1", "name": "Alice", "email": "a@test.com"})
    with pytest.raises(DuplicateEntityError) as exc_info:
        await sql_adapter.create({"id": "1", "name": "Bob", "email": "b@test.com"})
    error_msg = str(exc_info.value)
    assert "sqlite" not in error_msg.lower()
    assert "memory" not in error_msg.lower()
