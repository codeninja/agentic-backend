"""Motor/MongoDB adapter implementing the Repository protocol."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from ninja_core.schema.entity import EntitySchema

from ninja_persistence.adapters import _validate_limit
from ninja_persistence.exceptions import (
    ConnectionFailedError,
    DuplicateEntityError,
    PersistenceError,
    QueryError,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class VectorSidecar(Protocol):
    """Minimal protocol for a vector sidecar repository."""

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...
    async def upsert_embedding(self, id: str, embedding: list[float]) -> None: ...


class MongoAdapter:
    """Async MongoDB adapter backed by Motor.

    Implements the Repository protocol for document databases.

    Supports two vector search modes controlled by ``vector_mode``:

    - ``"native"``: Uses MongoDB Atlas Vector Search via the ``$vectorSearch``
      aggregation stage.  Embeddings are stored inline in each document under
      the ``_embedding`` field, and an Atlas Search index must exist on the
      collection.
    - ``"sidecar"`` (default): Delegates semantic search and embedding storage
      to an external vector adapter (Chroma/Milvus) passed as ``vector_sidecar``.

    Requires the ``motor`` optional dependency:
        pip install ninja-persistence[mongo]
    """

    def __init__(
        self,
        entity: EntitySchema,
        database: Any = None,
        *,
        vector_mode: str = "sidecar",
        vector_sidecar: VectorSidecar | None = None,
        embedding_dimensions: int = 1536,
        vector_index_name: str = "vector_index",
        embedding_field: str = "_embedding",
    ) -> None:
        self._entity = entity
        self._database = database
        self._collection_name = entity.collection_name or entity.name.lower()
        self._vector_mode = vector_mode
        self._vector_sidecar = vector_sidecar
        self._embedding_dimensions = embedding_dimensions
        self._vector_index_name = vector_index_name
        self._embedding_field = embedding_field

    @property
    def has_native_vector(self) -> bool:
        """True when vector_mode is 'native' (Atlas Vector Search)."""
        return self._vector_mode == "native"

    @property
    def has_vector_support(self) -> bool:
        """True when either native Atlas Vector Search or a sidecar is configured."""
        return self._vector_mode == "native" or self._vector_sidecar is not None

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
        """Retrieve multiple documents matching the given filters.

        Args:
            filters: MongoDB query filters.
            limit: Max documents to return (1–1000). Values above 1000 are
                   capped; values below 1 raise ``ValueError``.

        Raises:
            QueryError: If filter keys contain MongoDB operators (``$``-prefixed keys).
        """
        limit = _validate_limit(limit)
        if filters:
            _reject_mongo_operators(filters, self._entity.name)
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
                logger.error(
                    "Mongo update connection error for %s (id=%s): %s", self._entity.name, id, type(exc).__name__
                )
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
                logger.error(
                    "Mongo delete connection error for %s (id=%s): %s", self._entity.name, id, type(exc).__name__
                )
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

    # -- Semantic / Vector operations -----------------------------------------

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Perform semantic (vector similarity) search.

        Uses Atlas Vector Search ``$vectorSearch`` aggregation when
        ``vector_mode='native'``, otherwise delegates to the configured
        ``vector_sidecar``.

        Args:
            query: The search query or embedding vector.
            limit: Max results to return (1–1000). Values above 1000 are capped;
                   values below 1 raise ``ValueError``.
        """
        limit = _validate_limit(limit)
        if self._vector_mode == "native":
            return await self._atlas_vector_search(query, limit)
        if self._vector_sidecar is not None:
            return await self._vector_sidecar.search_semantic(query, limit)
        raise NotImplementedError(
            "Semantic search not available for MongoDB adapter. "
            "Configure a vector sidecar (Chroma/Milvus) or enable Atlas Vector Search (vector_mode='native')."
        )

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Insert or update the embedding vector for a document.

        In native mode, stores the embedding inline in the document under
        the configured ``embedding_field``.  In sidecar mode, delegates to
        the ``vector_sidecar``.  On sidecar failure, logs a warning but does
        not raise — best-effort consistency.
        """
        if self._vector_mode == "native":
            await self._atlas_upsert_embedding(id, embedding)
            return
        if self._vector_sidecar is not None:
            try:
                await self._vector_sidecar.upsert_embedding(id, embedding)
            except Exception:
                logger.warning(
                    "Sidecar upsert_embedding failed for %s (id=%s); primary store unaffected.",
                    self._entity.name,
                    id,
                    exc_info=True,
                )
            return
        raise NotImplementedError(
            "Embedding storage not available for MongoDB adapter. "
            "Configure a vector sidecar (Chroma/Milvus) or enable Atlas Vector Search (vector_mode='native')."
        )

    # -- Atlas Vector Search internals ----------------------------------------

    async def _atlas_upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Store an embedding inline in the document for Atlas Vector Search."""
        coll = self._get_collection()
        try:
            await coll.update_one(
                {"_id": id},
                {"$set": {self._embedding_field: embedding}},
                upsert=True,
            )
        except Exception as exc:
            if _is_connection_error(exc):
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="upsert_embedding",
                    detail="Database connection failed during embedding upsert.",
                    cause=exc,
                ) from exc
            logger.error(
                "Atlas upsert_embedding failed for %s (id=%s): %s",
                self._entity.name,
                id,
                type(exc).__name__,
            )
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="upsert_embedding",
                detail="Failed to upsert embedding in MongoDB.",
                cause=exc,
            ) from exc

    async def _atlas_vector_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search using Atlas Vector Search ``$vectorSearch`` aggregation stage.

        ``query`` must be a JSON-encoded list of floats (the embedding vector).
        Callers should pre-embed text queries via the model layer.
        """
        try:
            query_vec = json.loads(query) if isinstance(query, str) else query
            if not isinstance(query_vec, list):
                raise ValueError("Expected a list of floats")
        except (json.JSONDecodeError, ValueError) as exc:
            raise QueryError(
                entity_name=self._entity.name,
                operation="search_semantic",
                detail=(
                    "Atlas Vector Search requires an embedding vector (JSON list of floats). "
                    "Pre-embed the text query via the model layer before calling search_semantic()."
                ),
                cause=exc,
            ) from exc

        coll = self._get_collection()
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self._vector_index_name,
                    "path": self._embedding_field,
                    "queryVector": query_vec,
                    "numCandidates": limit * 10,
                    "limit": limit,
                }
            },
            {
                "$addFields": {
                    "_score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        try:
            results: list[dict[str, Any]] = []
            async for doc in coll.aggregate(pipeline):
                results.append(dict(doc))
            return results
        except Exception as exc:
            if _is_connection_error(exc):
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="search_semantic",
                    detail="Database connection failed during vector search.",
                    cause=exc,
                ) from exc
            logger.error(
                "Atlas vector search failed for %s: %s",
                self._entity.name,
                type(exc).__name__,
            )
            raise QueryError(
                entity_name=self._entity.name,
                operation="search_semantic",
                detail="Atlas Vector Search query failed.",
                cause=exc,
            ) from exc

    # -- Catch-up re-index utility --------------------------------------------

    async def reindex_missing_embeddings(
        self,
        embed_fn: Any,
        text_field: str = "name",
        batch_size: int = 100,
    ) -> int:
        """Re-index documents that are missing embeddings.

        In native mode, scans for documents where the embedding field is null
        or missing.  In sidecar mode, fetches all documents and upserts
        embeddings for each (the sidecar handles deduplication).

        Args:
            embed_fn: An async callable ``(str) -> list[float]`` that converts
                text to an embedding vector.
            text_field: The entity field to embed (default ``"name"``).
            batch_size: Number of documents to process per batch.

        Returns:
            The count of documents that were re-indexed.
        """
        if not self.has_vector_support:
            raise NotImplementedError(
                "Cannot reindex: no vector backend configured. "
                "Enable Atlas Vector Search (vector_mode='native') or provide a vector_sidecar."
            )

        reindexed = 0

        if self._vector_mode == "native":
            coll = self._get_collection()
            try:
                cursor = coll.find(
                    {"$or": [{self._embedding_field: None}, {self._embedding_field: {"$exists": False}}]}
                ).limit(batch_size)
                async for doc in cursor:
                    doc_id = doc.get("_id")
                    if doc_id is None:
                        continue
                    text = str(doc.get(text_field, ""))
                    if not text:
                        continue
                    embedding = await embed_fn(text)
                    await self.upsert_embedding(str(doc_id), embedding)
                    reindexed += 1
            except Exception as exc:
                if _is_connection_error(exc):
                    raise ConnectionFailedError(
                        entity_name=self._entity.name,
                        operation="reindex_missing_embeddings",
                        detail="Database connection failed during reindex scan.",
                        cause=exc,
                    ) from exc
                raise QueryError(
                    entity_name=self._entity.name,
                    operation="reindex_missing_embeddings",
                    detail="Failed to scan for missing embeddings.",
                    cause=exc,
                ) from exc
        elif self._vector_sidecar is not None:
            records = await self.find_many(limit=batch_size)
            for record in records:
                doc_id = record.get("_id")
                if doc_id is None:
                    continue
                text = str(record.get(text_field, ""))
                if not text:
                    continue
                embedding = await embed_fn(text)
                await self.upsert_embedding(str(doc_id), embedding)
                reindexed += 1

        return reindexed


def _reject_mongo_operators(filters: dict[str, Any], entity_name: str) -> None:
    """Raise ``QueryError`` if any filter key (recursively) starts with ``$``.

    This prevents NoSQL injection via MongoDB query operators such as
    ``$gt``, ``$ne``, ``$regex``, etc. that could be smuggled in through
    user-supplied filter dictionaries.
    """
    def _check(obj: Any) -> None:
        if isinstance(obj, dict):
            for key in obj:
                if isinstance(key, str) and key.startswith("$"):
                    raise QueryError(
                        entity_name=entity_name,
                        operation="find_many",
                        detail=f"Filter key '{key}' is not allowed: MongoDB operators are rejected for security.",
                    )
                _check(obj[key])
        elif isinstance(obj, list):
            for item in obj:
                _check(item)

    _check(filters)


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
