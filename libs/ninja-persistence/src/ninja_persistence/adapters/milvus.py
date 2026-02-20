"""Milvus vector adapter implementing the Repository protocol (stub)."""

from __future__ import annotations

from typing import Any

from ninja_core.schema.entity import EntitySchema


class MilvusVectorAdapter:
    """Milvus-backed vector store adapter.

    Implements the Repository protocol with native semantic search support.

    Requires the ``pymilvus`` optional dependency:
        pip install ninja-persistence[milvus]
    """

    def __init__(self, entity: EntitySchema, client: Any = None) -> None:
        self._entity = entity
        self._client = client
        self._collection_name = entity.collection_name or entity.name.lower()

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        raise NotImplementedError("MilvusVectorAdapter.find_by_id is not yet implemented.")

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError("MilvusVectorAdapter.find_many is not yet implemented.")

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("MilvusVectorAdapter.create is not yet implemented.")

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError("MilvusVectorAdapter.update is not yet implemented.")

    async def delete(self, id: str) -> bool:
        raise NotImplementedError("MilvusVectorAdapter.delete is not yet implemented.")

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError("MilvusVectorAdapter.search_semantic is not yet implemented.")

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        raise NotImplementedError("MilvusVectorAdapter.upsert_embedding is not yet implemented.")
