"""Motor/MongoDB adapter implementing the Repository protocol."""

from __future__ import annotations

import logging
from typing import Any

from ninja_core.schema.entity import EntitySchema

from ninja_persistence.exceptions import (
    ConnectionFailedError,
    DuplicateEntityError,
    PersistenceError,
    QueryError,
)

logger = logging.getLogger(__name__)


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
        """Return the Motor collection, raising if no database is configured."""
        if self._database is None:
            raise RuntimeError(
                "MongoAdapter requires a Motor database instance. Pass it via the `database` constructor parameter."
            )
        return self._database[self._collection_name]

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        """Retrieve a single document by ``_id``."""
        coll = self._get_collection()
        try:
            doc = await coll.find_one({"_id": id})
            return dict(doc) if doc else None
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error("Mongo find_by_id connection error for %s: %s", self._entity.name, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="find_by_id",
                    detail="Database connection failed during read.",
                    cause=exc,
                ) from exc
            logger.error("Mongo find_by_id failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_by_id",
                detail="Query execution failed.",
                cause=exc,
            ) from exc

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve multiple documents matching the given filters."""
        coll = self._get_collection()
        try:
            cursor = coll.find(filters or {}).limit(limit)
            return [dict(doc) async for doc in cursor]
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error("Mongo find_many connection error for %s: %s", self._entity.name, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="find_many",
                    detail="Database connection failed during read.",
                    cause=exc,
                ) from exc
            logger.error("Mongo find_many failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_many",
                detail="Query execution failed.",
                cause=exc,
            ) from exc

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new document and return the created entity."""
        coll = self._get_collection()
        try:
            await coll.insert_one(data)
            return data
        except Exception as exc:
            if _is_duplicate_key_error(exc):
                logger.error("Mongo create failed for %s: duplicate key", self._entity.name)
                raise DuplicateEntityError(
                    entity_name=self._entity.name,
                    operation="create",
                    detail="A document with the same key already exists.",
                    cause=exc,
                ) from exc
            if _is_connection_error(exc):
                logger.error("Mongo create connection error for %s: %s", self._entity.name, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="create",
                    detail="Database connection failed during insert.",
                    cause=exc,
                ) from exc
            logger.error("Mongo create failed for %s: %s", self._entity.name, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="create",
                detail="Insert operation failed.",
                cause=exc,
            ) from exc

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a partial update to an existing document."""
        coll = self._get_collection()
        try:
            result = await coll.update_one({"_id": id}, {"$set": patch})
            if result.matched_count == 0:
                return None
            return await self.find_by_id(id)
        except Exception as exc:
            if _is_duplicate_key_error(exc):
                logger.error("Mongo update failed for %s (id=%s): duplicate key", self._entity.name, id)
                raise DuplicateEntityError(
                    entity_name=self._entity.name,
                    operation="update",
                    detail="Update violates a uniqueness constraint.",
                    cause=exc,
                ) from exc
            if _is_connection_error(exc):
                logger.error("Mongo update connection error for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="update",
                    detail="Database connection failed during update.",
                    cause=exc,
                ) from exc
            logger.error("Mongo update failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="update",
                detail="Update operation failed.",
                cause=exc,
            ) from exc

    async def delete(self, id: str) -> bool:
        """Delete a document by ``_id``. Returns True if deleted."""
        coll = self._get_collection()
        try:
            result = await coll.delete_one({"_id": id})
            return result.deleted_count > 0
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error("Mongo delete connection error for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="delete",
                    detail="Database connection failed during delete.",
                    cause=exc,
                ) from exc
            logger.error("Mongo delete failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="delete",
                detail="Delete operation failed.",
                cause=exc,
            ) from exc

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


def _is_duplicate_key_error(exc: Exception) -> bool:
    """Check whether *exc* is a MongoDB duplicate-key error.

    Works with or without ``pymongo`` installed by inspecting the exception's
    class hierarchy names and the error code attribute used by PyMongo.
    """
    exc_type_name = type(exc).__name__
    if exc_type_name == "DuplicateKeyError":
        return True
    # PyMongo wraps duplicate key errors as WriteError with code 11000.
    if hasattr(exc, "code") and getattr(exc, "code", None) == 11000:
        return True
    return False


def _is_connection_error(exc: Exception) -> bool:
    """Check whether *exc* indicates a connection-level failure.

    Detects PyMongo ``ConnectionFailure``, ``ServerSelectionTimeoutError``, and
    similar network-layer exceptions without requiring the import.
    """
    type_names = {cls.__name__ for cls in type(exc).__mro__}
    return bool(type_names & {"ConnectionFailure", "ServerSelectionTimeoutError", "AutoReconnect", "NetworkTimeout"})
