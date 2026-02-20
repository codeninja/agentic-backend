"""Neo4j graph adapter implementing the Repository protocol (stub)."""

from __future__ import annotations

from typing import Any

from ninja_core.schema.entity import EntitySchema


class GraphAdapter:
    """Async Neo4j adapter for graph-backed entities.

    Implements the Repository protocol for graph databases.

    Requires the ``neo4j`` optional dependency:
        pip install ninja-persistence[graph]
    """

    def __init__(self, entity: EntitySchema, driver: Any = None) -> None:
        self._entity = entity
        self._driver = driver
        self._label = entity.collection_name or entity.name

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        raise NotImplementedError("GraphAdapter.find_by_id is not yet implemented.")

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError("GraphAdapter.find_many is not yet implemented.")

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("GraphAdapter.create is not yet implemented.")

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError("GraphAdapter.update is not yet implemented.")

    async def delete(self, id: str) -> bool:
        raise NotImplementedError("GraphAdapter.delete is not yet implemented.")

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError("GraphAdapter.search_semantic is not yet implemented.")

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        raise NotImplementedError("GraphAdapter.upsert_embedding is not yet implemented.")
