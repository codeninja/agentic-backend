"""Tests for the Neo4j GraphAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.graph import GraphAdapter


@pytest.fixture
def user_entity() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.GRAPH,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="email", field_type=FieldType.STRING, unique=True),
            FieldSchema(name="age", field_type=FieldType.INTEGER, nullable=True),
        ],
    )


def _make_mock_driver() -> MagicMock:
    """Build a mock Neo4j AsyncDriver with chainable session/run/result."""
    driver = MagicMock()
    session = AsyncMock()
    result = AsyncMock()

    # driver.session() returns an async context manager yielding `session`
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    driver.session.return_value = ctx

    session.run = AsyncMock(return_value=result)
    return driver


def _configure_result(driver: MagicMock, *, single: dict | None = None, data: list | None = None) -> None:
    """Configure the mock result returned by session.run()."""
    result = AsyncMock()
    if single is not None:
        result.single = AsyncMock(return_value=single)
    else:
        result.single = AsyncMock(return_value=None)

    if data is not None:
        result.data = AsyncMock(return_value=data)
    else:
        result.data = AsyncMock(return_value=[])

    # Replace the run mock to return our configured result
    ctx = driver.session.return_value
    session = ctx.__aenter__.return_value
    session.run = AsyncMock(return_value=result)


# --- Construction & validation ---


def test_label_from_entity_name(user_entity: EntitySchema):
    adapter = GraphAdapter(entity=user_entity)
    assert adapter._label == "User"


def test_label_from_collection_name():
    entity = EntitySchema(
        name="Product",
        storage_engine=StorageEngine.GRAPH,
        collection_name="products_v2",
        fields=[FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True)],
    )
    adapter = GraphAdapter(entity=entity)
    assert adapter._label == "products_v2"


def test_pk_field_resolved(user_entity: EntitySchema):
    adapter = GraphAdapter(entity=user_entity)
    assert adapter._pk_field == "id"


def test_driver_not_set_raises(user_entity: EntitySchema):
    adapter = GraphAdapter(entity=user_entity)
    with pytest.raises(RuntimeError, match="neo4j AsyncDriver"):
        adapter._get_driver()


# --- find_by_id ---


async def test_find_by_id(user_entity: EntitySchema):
    driver = _make_mock_driver()
    node_props = {"id": "1", "name": "Alice", "email": "alice@test.com", "age": 30}
    _configure_result(driver, single={"n": node_props})

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    found = await adapter.find_by_id("1")

    assert found is not None
    assert found["name"] == "Alice"
    assert found["id"] == "1"


async def test_find_by_id_not_found(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, single=None)

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    found = await adapter.find_by_id("nonexistent")

    assert found is None


# --- find_many ---


async def test_find_many(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, data=[
        {"n": {"id": "1", "name": "Alice", "email": "a@test.com", "age": 30}},
        {"n": {"id": "2", "name": "Bob", "email": "b@test.com", "age": 25}},
    ])

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    results = await adapter.find_many()

    assert len(results) == 2
    assert results[0]["name"] == "Alice"
    assert results[1]["name"] == "Bob"


async def test_find_many_with_filters(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, data=[
        {"n": {"id": "1", "name": "Alice", "email": "a@test.com", "age": 30}},
    ])

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    results = await adapter.find_many(filters={"age": 30})

    assert len(results) == 1
    # Verify the Cypher query contains a WHERE clause with the filter
    session = driver.session.return_value.__aenter__.return_value
    call_args = session.run.call_args
    query = call_args[0][0]
    assert "WHERE" in query
    assert "n.`age`" in query


async def test_find_many_empty(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, data=[])

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    results = await adapter.find_many()

    assert results == []


async def test_find_many_with_limit(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, data=[
        {"n": {"id": "1", "name": "Alice", "email": "a@test.com", "age": 30}},
    ])

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    await adapter.find_many(limit=1)

    session = driver.session.return_value.__aenter__.return_value
    call_args = session.run.call_args
    params = call_args[0][1]
    assert params["limit"] == 1


# --- create ---


async def test_create(user_entity: EntitySchema):
    driver = _make_mock_driver()
    data = {"id": "1", "name": "Alice", "email": "alice@test.com", "age": 30}
    _configure_result(driver, single={"n": data})

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    result = await adapter.create(data)

    assert result["id"] == "1"
    assert result["name"] == "Alice"

    # Verify Cypher CREATE was used
    session = driver.session.return_value.__aenter__.return_value
    query = session.run.call_args[0][0]
    assert "CREATE" in query


# --- update ---


async def test_update(user_entity: EntitySchema):
    driver = _make_mock_driver()
    updated_props = {"id": "1", "name": "Alice Updated", "email": "alice@test.com", "age": 31}
    _configure_result(driver, single={"n": updated_props})

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    result = await adapter.update("1", {"name": "Alice Updated", "age": 31})

    assert result is not None
    assert result["name"] == "Alice Updated"
    assert result["age"] == 31

    # Verify Cypher SET n += was used
    session = driver.session.return_value.__aenter__.return_value
    query = session.run.call_args[0][0]
    assert "SET n += $patch" in query


async def test_update_not_found(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, single=None)

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    result = await adapter.update("nonexistent", {"name": "Ghost"})

    assert result is None


# --- delete ---


async def test_delete(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, single={"deleted": 1})

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    result = await adapter.delete("1")

    assert result is True

    # Verify DETACH DELETE was used
    session = driver.session.return_value.__aenter__.return_value
    query = session.run.call_args[0][0]
    assert "DETACH DELETE" in query


async def test_delete_not_found(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, single={"deleted": 0})

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    result = await adapter.delete("nonexistent")

    assert result is False


# --- search_semantic ---


async def test_search_semantic_fulltext(user_entity: EntitySchema):
    """Full-text index search returns nodes with scores."""
    driver = _make_mock_driver()
    _configure_result(driver, data=[
        {"node": {"id": "1", "name": "Alice", "email": "a@test.com"}, "score": 0.95},
        {"node": {"id": "2", "name": "Alicia", "email": "al@test.com"}, "score": 0.80},
    ])

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    results = await adapter.search_semantic("Ali", limit=5)

    assert len(results) == 2
    assert results[0]["_score"] == 0.95
    assert results[0]["name"] == "Alice"


async def test_search_semantic_fallback_contains(user_entity: EntitySchema):
    """Falls back to CONTAINS search when full-text index is unavailable."""
    driver = _make_mock_driver()

    # First call (fulltext) raises an exception, second call (fallback) succeeds
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    driver.session.return_value = ctx

    fulltext_result = AsyncMock()
    fulltext_result.data = AsyncMock(side_effect=Exception("No such index"))

    fallback_result = AsyncMock()
    fallback_result.data = AsyncMock(return_value=[
        {"n": {"id": "1", "name": "Alice", "email": "a@test.com"}},
    ])

    session.run = AsyncMock(side_effect=[fulltext_result, fallback_result])

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    results = await adapter.search_semantic("Alice")

    assert len(results) == 1
    assert results[0]["name"] == "Alice"


async def test_search_semantic_no_string_fields():
    """Returns empty when there are no string fields for fallback search."""
    entity = EntitySchema(
        name="Counter",
        storage_engine=StorageEngine.GRAPH,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="count", field_type=FieldType.INTEGER),
        ],
    )
    driver = _make_mock_driver()

    # Fulltext index fails
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    driver.session.return_value = ctx

    fulltext_result = AsyncMock()
    fulltext_result.data = AsyncMock(side_effect=Exception("No such index"))
    session.run = AsyncMock(return_value=fulltext_result)

    adapter = GraphAdapter(entity=entity, driver=driver)
    # The only string field is "id" which has field_type STRING but we
    # include string/text fields, so id IS included. Let's use only INTEGER.
    entity_no_strings = EntitySchema(
        name="Numeric",
        storage_engine=StorageEngine.GRAPH,
        fields=[
            FieldSchema(name="id", field_type=FieldType.INTEGER, primary_key=True),
            FieldSchema(name="count", field_type=FieldType.INTEGER),
        ],
    )
    adapter2 = GraphAdapter(entity=entity_no_strings, driver=driver)
    results = await adapter2.search_semantic("test")
    assert results == []


# --- upsert_embedding ---


async def test_upsert_embedding(user_entity: EntitySchema):
    driver = _make_mock_driver()
    _configure_result(driver, single=None)

    adapter = GraphAdapter(entity=user_entity, driver=driver)
    await adapter.upsert_embedding("1", [0.1, 0.2, 0.3])

    session = driver.session.return_value.__aenter__.return_value
    call_args = session.run.call_args
    query = call_args[0][0]
    params = call_args[0][1]
    assert "SET n.embedding = $embedding" in query
    assert params["embedding"] == [0.1, 0.2, 0.3]
    assert params["id"] == "1"


# --- Protocol compliance ---


def test_graph_adapter_satisfies_repository_protocol(user_entity: EntitySchema):
    """GraphAdapter is recognized as a Repository at runtime."""
    from ninja_persistence.protocols import Repository
    adapter = GraphAdapter(entity=user_entity)
    assert isinstance(adapter, Repository)


# --- Custom label ---


async def test_custom_label():
    entity = EntitySchema(
        name="Product",
        storage_engine=StorageEngine.GRAPH,
        collection_name="products_v2",
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="title", field_type=FieldType.STRING),
        ],
    )
    driver = _make_mock_driver()
    data = {"id": "p1", "title": "Widget"}
    _configure_result(driver, single={"n": data})

    adapter = GraphAdapter(entity=entity, driver=driver)
    result = await adapter.create(data)

    assert result["id"] == "p1"
    session = driver.session.return_value.__aenter__.return_value
    query = session.run.call_args[0][0]
    assert "products_v2" in query
