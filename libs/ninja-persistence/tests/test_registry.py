"""Tests for the adapter registry."""

from unittest.mock import AsyncMock

from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.graph import GraphAdapter
from ninja_persistence.adapters.mongo import MongoAdapter
from ninja_persistence.adapters.sql import SQLAdapter
from ninja_persistence.connections import ConnectionManager, ConnectionProfile
from ninja_persistence.registry import AdapterRegistry


def _make_entity(engine: StorageEngine) -> EntitySchema:
    return EntitySchema(
        name="TestEntity",
        storage_engine=engine,
        fields=[FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True)],
    )


def test_registry_returns_sql_adapter():
    profiles = {"default": ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:")}
    mgr = ConnectionManager(profiles=profiles)
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.SQL)
    repo = registry.get_repository(entity)
    assert isinstance(repo, SQLAdapter)


def test_registry_returns_mongo_adapter():
    mgr = ConnectionManager()
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.MONGO)
    repo = registry.get_repository(entity)
    assert isinstance(repo, MongoAdapter)


def test_registry_returns_graph_adapter():
    mgr = ConnectionManager()
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.GRAPH)
    repo = registry.get_repository(entity)
    assert isinstance(repo, GraphAdapter)


def test_registry_returns_vector_adapter():
    from ninja_persistence.adapters.chroma import ChromaVectorAdapter

    mgr = ConnectionManager()
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.VECTOR)
    repo = registry.get_repository(entity)
    assert isinstance(repo, ChromaVectorAdapter)


def test_registry_override():
    mgr = ConnectionManager()
    registry = AdapterRegistry(mgr)

    mock_repo = AsyncMock()
    entity = _make_entity(StorageEngine.SQL)
    registry.register("TestEntity", mock_repo)

    repo = registry.get_repository(entity)
    assert repo is mock_repo
