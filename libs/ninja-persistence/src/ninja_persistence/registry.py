"""Engine routing — maps ASD StorageEngine to the correct adapter."""

from __future__ import annotations

from typing import Any

from ninja_core.schema.entity import EntitySchema, StorageEngine

from ninja_persistence.connections import ConnectionManager
from ninja_persistence.protocols import Repository


class AdapterRegistry:
    """Routes entity schemas to the correct persistence adapter.

    Given an entity's StorageEngine from the ASD, the registry returns
    a configured Repository instance backed by the appropriate adapter.
    """

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._connection_manager = connection_manager
        self._overrides: dict[str, Repository[Any]] = {}

    def register(self, entity_name: str, repository: Repository[Any]) -> None:
        """Register a custom repository override for an entity."""
        self._overrides[entity_name] = repository

    def get_repository(self, entity: EntitySchema, profile_name: str = "default") -> Repository[Any]:
        """Resolve the correct repository adapter for an entity.

        Checks overrides first, then falls back to engine-based routing.
        """
        if entity.name in self._overrides:
            return self._overrides[entity.name]

        engine = entity.storage_engine

        if engine == StorageEngine.SQL:
            from ninja_persistence.adapters.sql import SQLAdapter

            sql_engine = self._connection_manager.get_sql_engine(profile_name)
            return SQLAdapter(engine=sql_engine, entity=entity)

        if engine == StorageEngine.MONGO:
            from ninja_persistence.adapters.mongo import MongoAdapter

            return MongoAdapter(entity=entity)

        if engine == StorageEngine.GRAPH:
            from ninja_persistence.adapters.graph import GraphAdapter

            return GraphAdapter(entity=entity)

        if engine == StorageEngine.VECTOR:
            from ninja_persistence.adapters.chroma import ChromaVectorAdapter

            return ChromaVectorAdapter(entity=entity)

        raise ValueError(f"Unsupported storage engine: {engine}")
