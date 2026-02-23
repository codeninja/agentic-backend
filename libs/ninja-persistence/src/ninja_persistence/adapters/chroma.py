"""Chroma vector adapter implementing the Repository protocol."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ninja_core.schema.entity import EntitySchema

from ninja_persistence.adapters import _validate_limit, _validate_offset
from ninja_persistence.exceptions import (
    ConnectionFailedError,
    DuplicateEntityError,
    PersistenceError,
    QueryError,
)

logger = logging.getLogger(__name__)


class ChromaVectorAdapter:
    """Chroma-backed vector store adapter.

    Implements the Repository protocol with native semantic search support.
    All synchronous Chroma client calls are offloaded to a thread via
    ``asyncio.to_thread`` so that the asyncio event loop is never blocked.

    Requires the ``chromadb`` optional dependency:
        pip install ninja-persistence[chroma]
    """

    def __init__(self, entity: EntitySchema, client: Any = None) -> None:
        self._entity = entity
        self._client = client
        self._collection_name = entity.collection_name or entity.name.lower()

    async def _get_collection(self) -> Any:
        """Return the Chroma collection, raising if no client is configured.

        The synchronous ``get_or_create_collection`` call is offloaded to a
        thread so it does not block the event loop.
        """
        if self._client is None:
            raise RuntimeError(
                "ChromaVectorAdapter requires a Chroma client instance. Pass it via the `client` constructor parameter."
            )
        try:
            return await asyncio.to_thread(self._client.get_or_create_collection, name=self._collection_name)
        except Exception as exc:
            logger.error("Chroma collection access failed for %s: %s", self._entity.name, type(exc).__name__)
            raise ConnectionFailedError(
                entity_name=self._entity.name,
                operation="_get_collection",
                detail="Failed to access or create Chroma collection.",
                cause=exc,
            ) from exc

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        """Retrieve a single record by primary key."""
        try:
            coll = await self._get_collection()
            result = await asyncio.to_thread(coll.get, ids=[id])
        except PersistenceError:
            raise
        except Exception as exc:
            logger.error("Chroma find_by_id failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_by_id",
                detail="Failed to retrieve document from Chroma.",
                cause=exc,
            ) from exc
        if not result.get("ids"):
            return None
        doc: dict[str, Any] = {"id": id}
        metadatas = result.get("metadatas")
        if metadatas and len(metadatas) > 0 and metadatas[0] is not None:
            doc.update(metadatas[0])
        documents = result.get("documents")
        if documents and len(documents) > 0 and documents[0] is not None:
            doc["document"] = documents[0]
        return doc

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Retrieve multiple records matching the given filters.

        Args:
            filters: Chroma ``where`` filters.
            limit: Max records to return (1–1000). Values above 1000 are capped;
                   values below 1 raise ``ValueError``.
            offset: Number of records to skip before returning results.
                    Negative values raise ``ValueError``.
        """
        limit = _validate_limit(limit)
        offset = _validate_offset(offset)
        try:
            coll = await self._get_collection()
            kwargs: dict[str, Any] = {"limit": limit, "offset": offset}
            if filters and "where" in filters:
                kwargs["where"] = filters["where"]
            result = await asyncio.to_thread(coll.get, **kwargs)
        except PersistenceError:
            raise
        except Exception as exc:
            logger.error("Chroma find_many failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_many",
                detail="Failed to query documents from Chroma.",
                cause=exc,
            ) from exc
        docs: list[dict[str, Any]] = []
        for i, doc_id in enumerate(result["ids"]):
            doc: dict[str, Any] = {"id": doc_id}
            if result.get("metadatas") and i < len(result["metadatas"]):
                doc.update(result["metadatas"][i])
            if result.get("documents") and i < len(result["documents"]):
                doc["document"] = result["documents"][i]
            docs.append(doc)
        return docs

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new record and return the created entity."""
        try:
            coll = await self._get_collection()
            doc_id = data.get("id", "")
            document = data.get("document", "")
            metadata = {k: v for k, v in data.items() if k not in ("id", "document", "embedding")}
            embedding = data.get("embedding")
            kwargs: dict[str, Any] = {
                "ids": [doc_id],
                "documents": [document],
            }
            if metadata:
                kwargs["metadatas"] = [metadata]
            if embedding:
                kwargs["embeddings"] = [embedding]
            await asyncio.to_thread(coll.add, **kwargs)
        except PersistenceError:
            raise
        except Exception as exc:
            if _is_duplicate_id_error(exc):
                logger.error("Chroma create failed for %s: duplicate ID", self._entity.name)
                raise DuplicateEntityError(
                    entity_name=self._entity.name,
                    operation="create",
                    detail="A document with the same ID already exists in Chroma.",
                    cause=exc,
                ) from exc
            logger.error("Chroma create failed for %s: %s", self._entity.name, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="create",
                detail="Failed to add document to Chroma.",
                cause=exc,
            ) from exc
        return data

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a partial update to an existing record."""
        try:
            coll = await self._get_collection()
            kwargs: dict[str, Any] = {"ids": [id]}
            if "document" in patch:
                kwargs["documents"] = [patch["document"]]
            metadata = {k: v for k, v in patch.items() if k not in ("id", "document", "embedding")}
            if metadata:
                kwargs["metadatas"] = [metadata]
            if "embedding" in patch:
                kwargs["embeddings"] = [patch["embedding"]]
            await asyncio.to_thread(coll.update, **kwargs)
        except PersistenceError:
            raise
        except Exception as exc:
            logger.error("Chroma update failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="update",
                detail="Failed to update document in Chroma.",
                cause=exc,
            ) from exc
        return await self.find_by_id(id)

    async def delete(self, id: str) -> bool:
        """Delete a record by primary key. Returns True if deleted."""
        try:
            coll = await self._get_collection()
            await asyncio.to_thread(coll.delete, ids=[id])
            return True
        except PersistenceError:
            raise
        except Exception as exc:
            logger.error("Chroma delete failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="delete",
                detail="Failed to delete document from Chroma.",
                cause=exc,
            ) from exc

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Perform semantic (vector similarity) search.

        Args:
            query: The text query for similarity search.
            limit: Max results to return (1–1000). Values above 1000 are capped;
                   values below 1 raise ``ValueError``.
        """
        limit = _validate_limit(limit)
        try:
            coll = await self._get_collection()
            result = await asyncio.to_thread(coll.query, query_texts=[query], n_results=limit)
        except PersistenceError:
            raise
        except Exception as exc:
            logger.error("Chroma search_semantic failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="search_semantic",
                detail="Semantic search query failed in Chroma.",
                cause=exc,
            ) from exc
        docs: list[dict[str, Any]] = []
        ids = result.get("ids")
        if not ids or not ids[0]:
            return docs
        for i, doc_id in enumerate(ids[0]):
            doc: dict[str, Any] = {"id": doc_id}
            metadatas = result.get("metadatas")
            if metadatas and len(metadatas) > 0 and metadatas[0] and i < len(metadatas[0]) and metadatas[0][i] is not None:
                doc.update(metadatas[0][i])
            documents = result.get("documents")
            if documents and len(documents) > 0 and documents[0] and i < len(documents[0]) and documents[0][i] is not None:
                doc["document"] = documents[0][i]
            distances = result.get("distances")
            if distances and len(distances) > 0 and distances[0] and i < len(distances[0]) and distances[0][i] is not None:
                doc["_distance"] = distances[0][i]
            docs.append(doc)
        return docs

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Insert or update the embedding vector for a record."""
        try:
            coll = await self._get_collection()
            await asyncio.to_thread(coll.update, ids=[id], embeddings=[embedding])
        except PersistenceError:
            raise
        except Exception as exc:
            logger.error("Chroma upsert_embedding failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="upsert_embedding",
                detail="Failed to upsert embedding in Chroma.",
                cause=exc,
            ) from exc


def _is_duplicate_id_error(exc: Exception) -> bool:
    """Check whether *exc* indicates a Chroma duplicate-ID error.

    Chroma raises a ``ValueError`` whose message contains ``"already exists"``
    when adding a document with an existing ID.  This heuristic avoids
    importing Chroma internals.
    """
    if isinstance(exc, ValueError) and "already exists" in str(exc).lower():
        return True
    # Also check chromadb-specific exception type names.
    if type(exc).__name__ in ("DuplicateIDError", "IDAlreadyExistsError"):
        return True
    return False
