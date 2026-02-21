"""Motor/MongoDB adapter implementing the Repository protocol (stub)."""

from __future__ import annotations

from typing import Any

from ninja_core.schema.entity import EntitySchema


class MongoAdapter:
    """Async MongoDB adapter backed by Motor.

    Implements the Repository protocol for document databases.

    Requires the ``motor`` optional dependency:
        pip install ninja-persistence[mongo]
    """

    def __init__(self, entity: EntitySchema, database: Any = None) -> None:
        self._entity = entity
        self._database = database
        self._collection_name = entity.collection_name or entity.name.lower()

    def _get_collection(self) -> Any:
        if self._database is None:
            raise RuntimeError(
                "MongoAdapter requires a Motor database instance. Pass it via the `database` constructor parameter."
            )
        return self._database[self._collection_name]

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        coll = self._get_collection()
        doc = await coll.find_one({"_id": id})
        return dict(doc) if doc else None

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        coll = self._get_collection()
        cursor = coll.find(filters or {}).limit(limit)
        return [dict(doc) async for doc in cursor]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        coll = self._get_collection()
        await coll.insert_one(data)
        return data

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        coll = self._get_collection()
        result = await coll.update_one({"_id": id}, {"$set": patch})
        if result.matched_count == 0:
            return None
        return await self.find_by_id(id)

    async def delete(self, id: str) -> bool:
        coll = self._get_collection()
        result = await coll.delete_one({"_id": id})
        return result.deleted_count > 0

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Semantic search is not natively supported in MongoDB.

        Raises ``NotImplementedError`` directing callers to configure a vector
        sidecar (Chroma/Milvus) for the entity.
        """
        raise NotImplementedError(
            "Semantic search not available for MongoDB adapter. "
            "Configure a vector sidecar (Chroma/Milvus) for this entity to enable semantic search."
        )

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Embedding storage is not natively supported in MongoDB.

        Raises ``NotImplementedError`` directing callers to configure a vector
        sidecar (Chroma/Milvus) for the entity.
        """
        raise NotImplementedError(
            "Embedding storage not available for MongoDB adapter. "
            "Configure a vector sidecar (Chroma/Milvus) for this entity to manage embeddings."
        )
