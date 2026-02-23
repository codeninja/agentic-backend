"""Milvus vector adapter implementing the Repository protocol."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from ninja_core.schema.entity import EntitySchema

from ninja_persistence.adapters import _validate_limit, _validate_offset
from ninja_persistence.exceptions import (
    ConnectionFailedError,
    PersistenceError,
    QueryError,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIMENSION = 1536
_DEFAULT_METRIC_TYPE = "COSINE"
_VECTOR_FIELD = "embedding"
_DOCUMENT_FIELD = "document"
_ID_FIELD = "id"
_RESERVED_FIELDS = frozenset({_ID_FIELD, _DOCUMENT_FIELD, _VECTOR_FIELD})


class MilvusVectorAdapter:
    """Milvus-backed vector store adapter.

    Implements the Repository protocol with native semantic search support.

    The adapter auto-creates a Milvus collection on first use.  The collection
    schema contains:

    * ``id`` — VARCHAR primary key
    * ``document`` — VARCHAR for the main text content
    * ``embedding`` — FLOAT_VECTOR for the dense vector

    Additional metadata fields are stored via Milvus **dynamic fields**.

    Requires the ``pymilvus`` optional dependency::

        pip install ninja-persistence[milvus]
    """

    def __init__(
        self,
        entity: EntitySchema,
        client: Any = None,
        *,
        dimension: int | None = None,
        metric_type: str = _DEFAULT_METRIC_TYPE,
    ) -> None:
        self._entity = entity
        self._client = client
        self._collection_name = entity.collection_name or entity.name.lower()
        self._dimension = dimension or self._infer_dimension()
        self._metric_type = metric_type
        self._collection_ready = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _infer_dimension(self) -> int:
        """Derive vector dimensionality from the entity's EmbeddingConfig.

        Falls back to ``_DEFAULT_DIMENSION`` (1536) when no embedding
        configuration is present on any field.
        """
        for field in self._entity.fields:
            if field.embedding is not None:
                return field.embedding.dimensions
        return _DEFAULT_DIMENSION

    def _require_client(self) -> Any:
        """Return the pymilvus ``MilvusClient`` or raise."""
        if self._client is None:
            raise RuntimeError(
                "MilvusVectorAdapter requires a pymilvus MilvusClient instance. "
                "Pass it via the `client` constructor parameter."
            )
        return self._client

    async def _run_sync(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous pymilvus call in the default executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def _ensure_collection(self) -> None:
        """Create the Milvus collection if it does not already exist.

        Uses the quick ``create_collection`` helper which sets up schema,
        index, and loads the collection automatically.  Dynamic fields are
        enabled so arbitrary metadata can be inserted without upfront schema
        changes.
        """
        if self._collection_ready:
            return

        client = self._require_client()
        try:
            exists = await self._run_sync(client.has_collection, self._collection_name)
            if not exists:
                await self._run_sync(
                    client.create_collection,
                    collection_name=self._collection_name,
                    dimension=self._dimension,
                    primary_field_name=_ID_FIELD,
                    id_type="string",
                    vector_field_name=_VECTOR_FIELD,
                    metric_type=self._metric_type,
                    max_length=65_535,
                    auto_id=False,
                )
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("Milvus collection setup failed for %s: %s", self._entity.name, type(exc).__name__)
            raise ConnectionFailedError(
                entity_name=self._entity.name,
                operation="_ensure_collection",
                detail="Failed to access or create Milvus collection.",
                cause=exc,
            ) from exc
        self._collection_ready = True

    def _output_fields(self) -> list[str]:
        """Return the list of output fields to request from Milvus queries."""
        return [_DOCUMENT_FIELD, "*"]

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        """Normalise a Milvus result row to the adapter's return format.

        Strips internal Milvus keys that start with ``$`` while keeping
        all user-defined fields.
        """
        return {k: v for k, v in row.items() if not k.startswith("$")}

    # ------------------------------------------------------------------
    # Repository protocol
    # ------------------------------------------------------------------

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        """Retrieve a single record by primary key.

        Args:
            id: The primary key value.

        Returns:
            A dictionary of the record's fields, or ``None`` if not found.
        """
        await self._ensure_collection()
        client = self._require_client()
        try:
            results = await self._run_sync(
                client.get,
                collection_name=self._collection_name,
                ids=[id],
                output_fields=self._output_fields(),
            )
        except Exception as exc:
            logger.error("Milvus find_by_id failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_by_id",
                detail="Failed to retrieve record from Milvus.",
                cause=exc,
            ) from exc
        if not results:
            return None
        return self._row_to_dict(results[0])

    async def find_many(
        self, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Retrieve multiple records matching the given filters.

        Args:
            filters: Optional dict.  If it contains a ``"filter"`` key the
                value is forwarded as a Milvus boolean filter expression
                (e.g. ``"category == 'news'"``) .  A ``"where"`` key is also
                accepted for compatibility with the Chroma adapter.
            limit: Maximum number of records to return.
            offset: Number of records to skip before returning results.
                    Negative values raise ``ValueError``.

        Returns:
            A list of matching record dicts.
        """
        limit = _validate_limit(limit)
        offset = _validate_offset(offset)
        await self._ensure_collection()
        client = self._require_client()

        filter_expr = ""
        if filters:
            filter_expr = filters.get("filter", filters.get("where", ""))

        kwargs: dict[str, Any] = {
            "collection_name": self._collection_name,
            "output_fields": self._output_fields(),
            "limit": limit,
            "offset": offset,
        }
        if filter_expr:
            kwargs["filter"] = filter_expr
        else:
            # MilvusClient.query requires a filter; use a tautology to list all.
            kwargs["filter"] = f'{_ID_FIELD} != ""'

        try:
            results = await self._run_sync(client.query, **kwargs)
        except Exception as exc:
            logger.error("Milvus find_many failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_many",
                detail="Failed to query records from Milvus.",
                cause=exc,
            ) from exc
        return [self._row_to_dict(r) for r in results]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new record and return the created entity.

        The record dict may contain:

        * ``id`` — required primary key
        * ``document`` — main text content
        * ``embedding`` — optional pre-computed vector
        * Any other keys are stored as dynamic metadata fields.

        Args:
            data: Field values for the new record.

        Returns:
            The inserted record (echo of *data*).
        """
        await self._ensure_collection()
        client = self._require_client()

        row: dict[str, Any] = {_ID_FIELD: data.get(_ID_FIELD, "")}
        row[_DOCUMENT_FIELD] = data.get(_DOCUMENT_FIELD, "")

        embedding = data.get(_VECTOR_FIELD)
        if embedding is not None:
            row[_VECTOR_FIELD] = embedding
        else:
            # Milvus requires a vector on insert; supply a zero-vector as placeholder.
            row[_VECTOR_FIELD] = [0.0] * self._dimension

        # Copy remaining metadata fields.
        for k, v in data.items():
            if k not in _RESERVED_FIELDS:
                row[k] = v

        try:
            await self._run_sync(client.insert, collection_name=self._collection_name, data=[row])
        except Exception as exc:
            logger.error("Milvus create failed for %s: %s", self._entity.name, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="create",
                detail="Failed to insert record into Milvus.",
                cause=exc,
            ) from exc
        return data

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a partial update to an existing record.

        Milvus does not support field-level updates, so this method fetches the
        current record, merges the patch, and upserts the result.

        Args:
            id: The primary key of the record to update.
            patch: A mapping of field names to new values.

        Returns:
            The updated record dict, or ``None`` if the original was not found.
        """
        existing = await self.find_by_id(id)
        if existing is None:
            return None

        merged = {**existing, **patch, _ID_FIELD: id}

        client = self._require_client()
        row: dict[str, Any] = {_ID_FIELD: id}
        row[_DOCUMENT_FIELD] = merged.get(_DOCUMENT_FIELD, "")

        embedding = merged.get(_VECTOR_FIELD)
        if embedding is not None:
            row[_VECTOR_FIELD] = embedding
        else:
            row[_VECTOR_FIELD] = [0.0] * self._dimension

        for k, v in merged.items():
            if k not in _RESERVED_FIELDS:
                row[k] = v

        try:
            await self._run_sync(client.upsert, collection_name=self._collection_name, data=[row])
        except Exception as exc:
            logger.error("Milvus update failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="update",
                detail="Failed to update record in Milvus.",
                cause=exc,
            ) from exc
        return await self.find_by_id(id)

    async def delete(self, id: str) -> bool:
        """Delete a record by primary key.

        Args:
            id: The primary key value.

        Returns:
            ``True`` if the delete call was executed.
        """
        await self._ensure_collection()
        client = self._require_client()
        try:
            await self._run_sync(client.delete, collection_name=self._collection_name, ids=[id])
        except Exception as exc:
            logger.error("Milvus delete failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="delete",
                detail="Failed to delete record from Milvus.",
                cause=exc,
            ) from exc
        return True

    async def search_semantic(
        self, query: str, limit: int = 10, *, query_embedding: list[float] | None = None
    ) -> list[dict[str, Any]]:
        """Perform semantic (ANN) vector similarity search.

        The caller must supply a pre-computed ``query_embedding`` because Milvus
        does not embed text natively (unlike Chroma).  If ``query_embedding`` is
        ``None`` the method returns an empty list — the orchestrating agent is
        expected to embed the query text before calling this adapter.

        Args:
            query: The raw query text (informational; not used directly).
            limit: Maximum number of results.
            query_embedding: Pre-computed query vector.

        Returns:
            A list of result dicts, each containing the matched record's fields
            plus a ``_distance`` key with the similarity score.
        """
        if query_embedding is None:
            return []

        await self._ensure_collection()
        client = self._require_client()

        try:
            results = await self._run_sync(
                client.search,
                collection_name=self._collection_name,
                data=[query_embedding],
                limit=limit,
                output_fields=self._output_fields(),
            )
        except Exception as exc:
            logger.error("Milvus search_semantic failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="search_semantic",
                detail="Semantic search query failed in Milvus.",
                cause=exc,
            ) from exc

        docs: list[dict[str, Any]] = []
        if results and results[0]:
            for hit in results[0]:
                doc: dict[str, Any] = {_ID_FIELD: hit["id"], "_distance": hit["distance"]}
                entity = hit.get("entity", {})
                doc.update(self._row_to_dict(entity))
                docs.append(doc)
        return docs

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Insert or update the embedding vector for a record.

        If the record already exists its fields are preserved and only the
        embedding is replaced.  If it does not exist a new record with a
        blank document and the given embedding is created.

        Args:
            id: The primary key of the target record.
            embedding: The dense vector to store.
        """
        await self._ensure_collection()
        client = self._require_client()

        existing = await self.find_by_id(id)
        if existing is not None:
            row = {**existing, _VECTOR_FIELD: embedding, _ID_FIELD: id}
        else:
            row = {_ID_FIELD: id, _DOCUMENT_FIELD: "", _VECTOR_FIELD: embedding}

        try:
            await self._run_sync(client.upsert, collection_name=self._collection_name, data=[row])
        except Exception as exc:
            logger.error("Milvus upsert_embedding failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="upsert_embedding",
                detail="Failed to upsert embedding in Milvus.",
                cause=exc,
            ) from exc
