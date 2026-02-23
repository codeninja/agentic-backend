"""Neo4j graph adapter implementing the Repository protocol."""

from __future__ import annotations

import logging
from typing import Any

from ninja_core.schema.entity import EntitySchema

from ninja_persistence.adapters import _validate_limit, _validate_offset
from ninja_persistence.exceptions import (
    ConnectionFailedError,
    PersistenceError,
    QueryError,
)

logger = logging.getLogger(__name__)


class GraphAdapter:
    """Async Neo4j adapter for graph-backed entities.

    Implements the Repository protocol for graph databases. Nodes are stored
    with a label derived from ``entity.collection_name`` (or ``entity.name``),
    and all entity fields become node properties.

    Requires the ``neo4j`` optional dependency:
        pip install ninja-persistence[graph]
    """

    def __init__(self, entity: EntitySchema, driver: Any = None) -> None:
        self._entity = entity
        self._driver = driver
        self._label = entity.collection_name or entity.name
        self._pk_field = self._resolve_pk_field()

    def _resolve_pk_field(self) -> str:
        """Return the name of the primary key field from the entity schema."""
        for field in self._entity.fields:
            if field.primary_key:
                return field.name
        return "id"

    def _get_driver(self) -> Any:
        """Return the Neo4j async driver, raising if not configured."""
        if self._driver is None:
            raise RuntimeError(
                "GraphAdapter requires a neo4j AsyncDriver instance. Pass it via the `driver` constructor parameter."
            )
        return self._driver

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        """Retrieve a single node by its primary key property.

        Args:
            id: The value of the primary key property to match.

        Returns:
            A dict of node properties, or ``None`` if no matching node exists.
        """
        driver = self._get_driver()
        query = f"MATCH (n:`{self._label}`) WHERE n.`{self._pk_field}` = $id RETURN n"
        try:
            async with driver.session() as session:
                result = await session.run(query, {"id": id})
                record = await result.single()
                if record is None:
                    return None
                return dict(record["n"])
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error("Graph find_by_id connection error for %s: %s", self._entity.name, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="find_by_id",
                    detail="Neo4j connection failed during read.",
                    cause=exc,
                ) from exc
            logger.error("Graph find_by_id failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_by_id",
                detail="Cypher query execution failed.",
                cause=exc,
            ) from exc

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Retrieve multiple nodes matching optional property filters.

        Args:
            filters: A dict of property name/value pairs to match exactly.
                     If ``None`` or empty, all nodes with the entity label
                     are returned.
            limit: Maximum number of nodes to return.
            offset: Number of nodes to skip before returning results.
                    Negative values raise ``ValueError``.

        Returns:
            A list of dicts, each representing a matched node's properties.
        """
        limit = _validate_limit(limit)
        offset = _validate_offset(offset)
        driver = self._get_driver()
        params: dict[str, Any] = {"limit": limit, "skip": offset}

        if filters:
            where_clauses = []
            for i, (key, value) in enumerate(filters.items()):
                param_name = f"f{i}"
                where_clauses.append(f"n.`{key}` = ${param_name}")
                params[param_name] = value
            where_str = " AND ".join(where_clauses)
            query = f"MATCH (n:`{self._label}`) WHERE {where_str} RETURN n SKIP $skip LIMIT $limit"
        else:
            query = f"MATCH (n:`{self._label}`) RETURN n SKIP $skip LIMIT $limit"

        try:
            async with driver.session() as session:
                result = await session.run(query, params)
                records = await result.data()
                return [dict(record["n"]) for record in records]
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error("Graph find_many connection error for %s: %s", self._entity.name, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="find_many",
                    detail="Neo4j connection failed during read.",
                    cause=exc,
                ) from exc
            logger.error("Graph find_many failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_many",
                detail="Cypher query execution failed.",
                cause=exc,
            ) from exc

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new node with the given properties.

        Args:
            data: A dict of property name/value pairs. Must include the
                  primary key field.

        Returns:
            The created node's properties as a dict.
        """
        driver = self._get_driver()
        query = f"CREATE (n:`{self._label}` $props) RETURN n"
        try:
            async with driver.session() as session:
                result = await session.run(query, {"props": data})
                record = await result.single()
                return dict(record["n"]) if record else data
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error("Graph create connection error for %s: %s", self._entity.name, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="create",
                    detail="Neo4j connection failed during create.",
                    cause=exc,
                ) from exc
            logger.error("Graph create failed for %s: %s", self._entity.name, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="create",
                detail="Failed to create node in Neo4j.",
                cause=exc,
            ) from exc

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a partial update to an existing node.

        Uses the Cypher ``+=`` operator to merge the patch into the node's
        existing properties without removing unmentioned keys.

        Args:
            id: The primary key value of the node to update.
            patch: A dict of property name/value pairs to set or overwrite.

        Returns:
            The updated node's full properties as a dict, or ``None`` if
            no node matched the given id.
        """
        driver = self._get_driver()
        query = f"MATCH (n:`{self._label}`) WHERE n.`{self._pk_field}` = $id SET n += $patch RETURN n"
        try:
            async with driver.session() as session:
                result = await session.run(query, {"id": id, "patch": patch})
                record = await result.single()
                if record is None:
                    return None
                return dict(record["n"])
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error(
                    "Graph update connection error for %s (id=%s): %s", self._entity.name, id, type(exc).__name__
                )
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="update",
                    detail="Neo4j connection failed during update.",
                    cause=exc,
                ) from exc
            logger.error("Graph update failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="update",
                detail="Failed to update node in Neo4j.",
                cause=exc,
            ) from exc

    async def delete(self, id: str) -> bool:
        """Delete a node and its relationships by primary key.

        Uses ``DETACH DELETE`` to remove the node along with any
        relationships attached to it, preventing orphaned edges.

        Args:
            id: The primary key value of the node to delete.

        Returns:
            ``True`` if a node was deleted, ``False`` if no node matched.
        """
        driver = self._get_driver()
        query = f"MATCH (n:`{self._label}`) WHERE n.`{self._pk_field}` = $id DETACH DELETE n RETURN count(n) AS deleted"
        try:
            async with driver.session() as session:
                result = await session.run(query, {"id": id})
                record = await result.single()
                return record is not None and record["deleted"] > 0
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error(
                    "Graph delete connection error for %s (id=%s): %s", self._entity.name, id, type(exc).__name__
                )
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="delete",
                    detail="Neo4j connection failed during delete.",
                    cause=exc,
                ) from exc
            logger.error("Graph delete failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="delete",
                detail="Failed to delete node from Neo4j.",
                cause=exc,
            ) from exc

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Perform semantic search using a Neo4j full-text index.

        Falls back to a case-insensitive ``CONTAINS`` search across all
        string-typed fields if no full-text index named
        ``{label}_fulltext`` is available.

        For true vector similarity search, use a sidecar vector adapter or
        configure a Neo4j vector index externally.

        Args:
            query: The search query string.
            limit: Maximum number of results to return.

        Returns:
            A list of matching node property dicts, each augmented with a
            ``_score`` key when a full-text index is used.
        """
        driver = self._get_driver()
        index_name = f"{self._label}_fulltext"

        # Try full-text index search first.
        ft_query = "CALL db.index.fulltext.queryNodes($index, $query) YIELD node, score RETURN node, score LIMIT $limit"
        try:
            async with driver.session() as session:
                result = await session.run(ft_query, {"index": index_name, "query": query, "limit": limit})
                records = await result.data()
                if records:
                    return [{**dict(r["node"]), "_score": r["score"]} for r in records]
        except Exception:
            # Full-text index not available; fall through to CONTAINS fallback.
            pass

        # Fallback: case-insensitive CONTAINS across string fields.
        string_fields = [f.name for f in self._entity.fields if f.field_type.value in ("string", "text")]
        if not string_fields:
            return []

        or_clauses = " OR ".join(f"toLower(toString(n.`{fname}`)) CONTAINS toLower($query)" for fname in string_fields)
        fallback_query = f"MATCH (n:`{self._label}`) WHERE {or_clauses} RETURN n LIMIT $limit"
        try:
            async with driver.session() as session:
                result = await session.run(fallback_query, {"query": query, "limit": limit})
                records = await result.data()
                return [dict(r["n"]) for r in records]
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error("Graph search_semantic connection error for %s: %s", self._entity.name, type(exc).__name__)
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="search_semantic",
                    detail="Neo4j connection failed during semantic search.",
                    cause=exc,
                ) from exc
            logger.error("Graph search_semantic failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="search_semantic",
                detail="Semantic search query failed in Neo4j.",
                cause=exc,
            ) from exc

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Store an embedding vector as a node property.

        Sets the ``embedding`` property on the node identified by the
        given primary key. This property can be used with a Neo4j vector
        index for approximate nearest-neighbor search.

        Args:
            id: The primary key value of the node to update.
            embedding: The embedding vector as a list of floats.
        """
        driver = self._get_driver()
        query = f"MATCH (n:`{self._label}`) WHERE n.`{self._pk_field}` = $id SET n.embedding = $embedding"
        try:
            async with driver.session() as session:
                await session.run(query, {"id": id, "embedding": embedding})
        except Exception as exc:
            if _is_connection_error(exc):
                logger.error(
                    "Graph upsert_embedding connection error for %s (id=%s): %s",
                    self._entity.name,
                    id,
                    type(exc).__name__,
                )
                raise ConnectionFailedError(
                    entity_name=self._entity.name,
                    operation="upsert_embedding",
                    detail="Neo4j connection failed during embedding upsert.",
                    cause=exc,
                ) from exc
            logger.error("Graph upsert_embedding failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="upsert_embedding",
                detail="Failed to upsert embedding in Neo4j.",
                cause=exc,
            ) from exc


def _is_connection_error(exc: Exception) -> bool:
    """Check whether *exc* indicates a Neo4j connection-level failure.

    Detects ``ServiceUnavailable``, ``SessionExpired``, and similar
    neo4j-driver network exceptions without requiring the import.
    """
    type_names = {cls.__name__ for cls in type(exc).__mro__}
    return bool(type_names & {"ServiceUnavailable", "SessionExpired", "DriverError"})
