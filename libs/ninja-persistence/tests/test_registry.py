"""Tests for the adapter registry."""

from unittest.mock import AsyncMock

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.sql import SQLAdapter
from ninja_persistence.connections import ConnectionManager, ConnectionProfile
from ninja_persistence.registry import AdapterRegistry


def _make_entity(engine: StorageEngine) -> EntitySchema:
    return EntitySchema(
        name="TestEntity",
        storage_engine=engine,
        fields=[FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True)],
    )


def _profile(engine: str, url: str, **options: object) -> ConnectionProfile:
    return ConnectionProfile.model_validate(
        {"engine": engine, "url": url, "options": options},
        context={"allow_private_hosts": True},
    )


def test_registry_returns_sql_adapter():
    profiles = {"default": _profile("sql", "sqlite+aiosqlite:///:memory:")}
    mgr = ConnectionManager(profiles=profiles)
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.SQL)
    repo = registry.get_repository(entity)
    assert isinstance(repo, SQLAdapter)


def test_registry_returns_mongo_adapter_with_database():
    """Registry should pass the Motor database to MongoAdapter."""
    from ninja_persistence.adapters.mongo import MongoAdapter

    profiles = {"default": _profile("mongo", "mongodb://localhost:27017/testdb", database="testdb")}
    mgr = ConnectionManager(profiles=profiles)
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.MONGO)
    repo = registry.get_repository(entity)
    assert isinstance(repo, MongoAdapter)
    assert repo._database is not None


def test_registry_returns_vector_adapter_with_client():
    """Registry should pass the Chroma client to ChromaVectorAdapter."""
    from ninja_persistence.adapters.chroma import ChromaVectorAdapter

    profiles = {"default": _profile("vector", "chroma://localhost")}
    mgr = ConnectionManager(profiles=profiles)
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.VECTOR)
    repo = registry.get_repository(entity)
    assert isinstance(repo, ChromaVectorAdapter)
    assert repo._client is not None


def test_registry_returns_graph_adapter_with_driver():
    """Registry should pass the Neo4j driver to GraphAdapter."""
    from ninja_persistence.adapters.graph import GraphAdapter

    profiles = {"default": _profile("graph", "bolt://localhost:7687", username="neo4j", password="test")}
    mgr = ConnectionManager(profiles=profiles)
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.GRAPH)
    repo = registry.get_repository(entity)
    assert isinstance(repo, GraphAdapter)
    assert repo._driver is not None


def test_registry_raises_on_missing_profile():
    """Registry should raise KeyError when no connection profile exists for the engine."""
    mgr = ConnectionManager()
    registry = AdapterRegistry(mgr)

    entity = _make_entity(StorageEngine.MONGO)
    with pytest.raises(KeyError, match="Connection profile 'default' not found"):
        registry.get_repository(entity)


def test_registry_override():
    mgr = ConnectionManager()
    registry = AdapterRegistry(mgr)

    mock_repo = AsyncMock()
    entity = _make_entity(StorageEngine.SQL)
    registry.register("TestEntity", mock_repo)

    repo = registry.get_repository(entity)
    assert repo is mock_repo
