"""SQLAlchemy async adapter implementing the Repository protocol."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import sqlalchemy as sa
from ninja_core.schema.entity import EntitySchema, FieldType
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ninja_persistence.exceptions import (
    ConnectionFailedError,
    DuplicateEntityError,
    PersistenceError,
    QueryError,
    TransactionError,
)

logger = logging.getLogger(__name__)

_FIELD_TYPE_MAP: dict[FieldType, type[sa.types.TypeEngine]] = {
    FieldType.STRING: sa.String,
    FieldType.TEXT: sa.Text,
    FieldType.INTEGER: sa.Integer,
    FieldType.FLOAT: sa.Float,
    FieldType.BOOLEAN: sa.Boolean,
    FieldType.DATETIME: sa.DateTime,
    FieldType.DATE: sa.Date,
    FieldType.UUID: sa.String,
    FieldType.JSON: sa.JSON,
    FieldType.ARRAY: sa.JSON,
    FieldType.BINARY: sa.LargeBinary,
    FieldType.ENUM: sa.String,
}


@runtime_checkable
class VectorSidecar(Protocol):
    """Minimal protocol for a vector sidecar repository."""

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...
    async def upsert_embedding(self, id: str, embedding: list[float]) -> None: ...


def _is_postgres(engine: AsyncEngine) -> bool:
    """Detect whether the engine is connected to PostgreSQL."""
    url = str(engine.url)
    return url.startswith("postgresql") or "+asyncpg" in url or "+psycopg" in url


def _build_table(entity: EntitySchema, metadata: sa.MetaData) -> sa.Table:
    """Dynamically build a SQLAlchemy Table from an EntitySchema."""
    table_name = entity.collection_name or entity.name.lower()
    columns: list[sa.Column] = []

    # Types that don't require a length argument
    _no_length_types = (sa.Text, sa.DateTime, sa.Date, sa.Integer, sa.Float, sa.Boolean, sa.JSON, sa.LargeBinary)

    for field in entity.fields:
        sa_type = _FIELD_TYPE_MAP.get(field.field_type, sa.String)
        col = sa.Column(
            field.name,
            sa_type() if sa_type in _no_length_types else sa_type(255),
            primary_key=field.primary_key,
            nullable=field.nullable,
            unique=field.unique,
            index=field.indexed,
        )
        columns.append(col)

    return sa.Table(table_name, metadata, *columns)


def _build_embedding_table(
    base_table_name: str, metadata: sa.MetaData, dimensions: int, vector_type: Any
) -> sa.Table:
    """Build the companion ``_embeddings`` table for pgvector storage."""
    return sa.Table(
        f"{base_table_name}_embeddings",
        metadata,
        sa.Column("record_id", sa.String(255), primary_key=True),
        sa.Column("embedding", vector_type(dimensions)),
    )


def _get_pk_column(table: sa.Table) -> sa.Column:
    """Return the primary key column of a table."""
    pk_cols = list(table.primary_key.columns)
    if not pk_cols:
        raise ValueError(f"Table '{table.name}' has no primary key column.")
    return pk_cols[0]


class SQLAdapter:
    """Async SQL adapter backed by SQLAlchemy.

    Implements the Repository protocol for relational databases.

    When PostgreSQL is detected and ``pgvector`` is installed, semantic search
    and embedding storage use a native ``_embeddings`` companion table with
    the ``vector`` column type.

    For non-Postgres engines, an optional ``vector_sidecar`` (any object
    implementing ``search_semantic`` and ``upsert_embedding``) is used as
    fallback.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        entity: EntitySchema,
        *,
        vector_sidecar: VectorSidecar | None = None,
        embedding_dimensions: int = 1536,
    ) -> None:
        self._engine = engine
        self._entity = entity
        self._metadata = sa.MetaData()
        self._table = _build_table(entity, self._metadata)
        self._vector_sidecar = vector_sidecar
        self._embedding_dimensions = embedding_dimensions

        # pgvector support
        self._pgvector_available = False
        self._embedding_table: sa.Table | None = None
        self._vector_type: Any = None

        if _is_postgres(engine):
            try:
                from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]

                self._pgvector_available = True
                self._vector_type = Vector
                base_name = entity.collection_name or entity.name.lower()
                self._embedding_table = _build_embedding_table(
                    base_name, self._metadata, embedding_dimensions, Vector
                )
            except ImportError:
                logger.debug(
                    "pgvector not installed; pgvector features disabled for %s. "
                    "Install with: pip install ninja-persistence[pgvector]",
                    entity.name,
                )

    @property
    def table(self) -> sa.Table:
        return self._table

    @property
    def has_native_vector(self) -> bool:
        """True when pgvector is available and engine is PostgreSQL."""
        return self._pgvector_available

    @property
    def has_vector_support(self) -> bool:
        """True when either pgvector or a sidecar is configured."""
        return self._pgvector_available or self._vector_sidecar is not None

    async def ensure_table(self) -> None:
        """Create the table (and embedding table if pgvector) if they do not exist."""
        async with self._engine.begin() as conn:
            if self._pgvector_available:
                await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(self._metadata.create_all)

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        """Retrieve a single record by primary key."""
        pk = _get_pk_column(self._table)
        stmt = self._table.select().where(pk == id)
        try:
            async with AsyncSession(self._engine) as session:
                result = await session.execute(stmt)
                row = result.mappings().first()
                return dict(row) if row else None
        except OperationalError as exc:
            logger.error("SQL find_by_id failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise ConnectionFailedError(
                entity_name=self._entity.name,
                operation="find_by_id",
                detail="Database connection failed during read.",
                cause=exc,
            ) from exc
        except SQLAlchemyError as exc:
            logger.error("SQL find_by_id failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_by_id",
                detail="Query execution failed.",
                cause=exc,
            ) from exc

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve multiple records matching the given filters."""
        stmt = self._table.select().limit(limit)
        if filters:
            for col_name, value in filters.items():
                if col_name in self._table.c:
                    stmt = stmt.where(self._table.c[col_name] == value)
        try:
            async with AsyncSession(self._engine) as session:
                result = await session.execute(stmt)
                return [dict(row) for row in result.mappings().all()]
        except OperationalError as exc:
            logger.error("SQL find_many failed for %s: %s", self._entity.name, type(exc).__name__)
            raise ConnectionFailedError(
                entity_name=self._entity.name,
                operation="find_many",
                detail="Database connection failed during read.",
                cause=exc,
            ) from exc
        except SQLAlchemyError as exc:
            logger.error("SQL find_many failed for %s: %s", self._entity.name, type(exc).__name__)
            raise QueryError(
                entity_name=self._entity.name,
                operation="find_many",
                detail="Query execution failed.",
                cause=exc,
            ) from exc

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new record and return the created entity."""
        stmt = self._table.insert().values(**data)
        try:
            async with self._engine.begin() as conn:
                await conn.execute(stmt)
        except IntegrityError as exc:
            logger.error("SQL create failed for %s: duplicate or constraint violation", self._entity.name)
            raise DuplicateEntityError(
                entity_name=self._entity.name,
                operation="create",
                detail="A record with the same key or unique constraint already exists.",
                cause=exc,
            ) from exc
        except OperationalError as exc:
            logger.error("SQL create failed for %s: %s", self._entity.name, type(exc).__name__)
            raise ConnectionFailedError(
                entity_name=self._entity.name,
                operation="create",
                detail="Database connection failed during insert.",
                cause=exc,
            ) from exc
        except SQLAlchemyError as exc:
            logger.error("SQL create failed for %s: %s", self._entity.name, type(exc).__name__)
            raise TransactionError(
                entity_name=self._entity.name,
                operation="create",
                detail="Insert transaction failed.",
                cause=exc,
            ) from exc
        return data

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a partial update to an existing record."""
        pk = _get_pk_column(self._table)
        stmt = self._table.update().where(pk == id).values(**patch)
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(stmt)
                if result.rowcount == 0:
                    return None
        except IntegrityError as exc:
            logger.error("SQL update failed for %s (id=%s): constraint violation", self._entity.name, id)
            raise DuplicateEntityError(
                entity_name=self._entity.name,
                operation="update",
                detail="Update violates a uniqueness constraint.",
                cause=exc,
            ) from exc
        except OperationalError as exc:
            logger.error("SQL update failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise ConnectionFailedError(
                entity_name=self._entity.name,
                operation="update",
                detail="Database connection failed during update.",
                cause=exc,
            ) from exc
        except SQLAlchemyError as exc:
            logger.error("SQL update failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise TransactionError(
                entity_name=self._entity.name,
                operation="update",
                detail="Update transaction failed.",
                cause=exc,
            ) from exc
        return await self.find_by_id(id)

    async def delete(self, id: str) -> bool:
        """Delete a record by primary key. Returns True if deleted."""
        pk = _get_pk_column(self._table)
        stmt = self._table.delete().where(pk == id)
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(stmt)
                return result.rowcount > 0
        except OperationalError as exc:
            logger.error("SQL delete failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise ConnectionFailedError(
                entity_name=self._entity.name,
                operation="delete",
                detail="Database connection failed during delete.",
                cause=exc,
            ) from exc
        except SQLAlchemyError as exc:
            logger.error("SQL delete failed for %s (id=%s): %s", self._entity.name, id, type(exc).__name__)
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="delete",
                detail="Delete operation failed.",
                cause=exc,
            ) from exc

    # -- Semantic / Vector operations -----------------------------------------

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Perform semantic (vector similarity) search.

        Uses pgvector cosine distance when PostgreSQL + pgvector is available,
        otherwise delegates to the configured ``vector_sidecar``.
        """
        if self._pgvector_available:
            return await self._pgvector_search(query, limit)
        if self._vector_sidecar is not None:
            return await self._vector_sidecar.search_semantic(query, limit)
        raise NotImplementedError(
            "Semantic search not available for SQL adapter. "
            "Configure a vector sidecar (Chroma/Milvus) for this entity to enable semantic search."
        )

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Insert or update the embedding vector for a record.

        Writes to pgvector natively on PostgreSQL, otherwise delegates to
        the ``vector_sidecar``.  On sidecar failure, logs a warning but does
        not roll back the primary store — best-effort consistency.
        """
        if self._pgvector_available:
            await self._pgvector_upsert(id, embedding)
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
            "Embedding storage not available for SQL adapter. "
            "Configure a vector sidecar (Chroma/Milvus) for this entity to manage embeddings."
        )

    # -- pgvector internals ---------------------------------------------------

    async def _pgvector_upsert(self, id: str, embedding: list[float]) -> None:
        """Insert or update an embedding row in the pgvector companion table."""
        assert self._embedding_table is not None  # noqa: S101
        tbl = self._embedding_table
        try:
            async with self._engine.begin() as conn:
                # Try insert first; on conflict update the embedding.
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(tbl).values(record_id=id, embedding=embedding)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["record_id"],
                    set_={"embedding": embedding},
                )
                await conn.execute(stmt)
        except SQLAlchemyError as exc:
            logger.error(
                "pgvector upsert_embedding failed for %s (id=%s): %s",
                self._entity.name,
                id,
                type(exc).__name__,
            )
            raise PersistenceError(
                entity_name=self._entity.name,
                operation="upsert_embedding",
                detail="Failed to upsert embedding in pgvector.",
                cause=exc,
            ) from exc

    async def _pgvector_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search by cosine distance in the pgvector companion table.

        Note: ``query`` is expected to already be an embedding (JSON list of
        floats serialised as a string) **or** callers should pre-embed the
        text query before calling.  For text-to-embedding conversion, use the
        model layer.  This method accepts the raw query string and attempts to
        parse it as a JSON vector; if it is not valid JSON, a ``QueryError``
        is raised indicating that an embedding vector is required.
        """
        import json

        assert self._embedding_table is not None  # noqa: S101
        tbl = self._embedding_table
        pk = _get_pk_column(self._table)

        try:
            query_vec = json.loads(query) if isinstance(query, str) else query
            if not isinstance(query_vec, list):
                raise ValueError("Expected a list of floats")
        except (json.JSONDecodeError, ValueError) as exc:
            raise QueryError(
                entity_name=self._entity.name,
                operation="search_semantic",
                detail=(
                    "pgvector search requires an embedding vector (JSON list of floats). "
                    "Pre-embed the text query via the model layer before calling search_semantic()."
                ),
                cause=exc,
            ) from exc

        try:
            cosine_distance = tbl.c.embedding.cosine_distance(query_vec)
            emb_stmt = (
                sa.select(tbl.c.record_id, cosine_distance.label("distance"))
                .order_by(cosine_distance)
                .limit(limit)
            )
            async with AsyncSession(self._engine) as session:
                emb_result = await session.execute(emb_stmt)
                rows = emb_result.mappings().all()

            results: list[dict[str, Any]] = []
            for row in rows:
                record = await self.find_by_id(row["record_id"])
                if record is not None:
                    record["_distance"] = float(row["distance"])
                    results.append(record)
            return results
        except PersistenceError:
            raise
        except SQLAlchemyError as exc:
            logger.error(
                "pgvector search_semantic failed for %s: %s",
                self._entity.name,
                type(exc).__name__,
            )
            raise QueryError(
                entity_name=self._entity.name,
                operation="search_semantic",
                detail="pgvector semantic search query failed.",
                cause=exc,
            ) from exc

    # -- Catch-up re-index utility --------------------------------------------

    async def reindex_missing_embeddings(
        self,
        embed_fn: Any,
        text_field: str = "name",
        batch_size: int = 100,
    ) -> int:
        """Re-index records that are missing embeddings.

        Scans the primary table for records without a corresponding row in the
        embeddings table (pgvector) or sidecar, calls ``embed_fn(text) -> list[float]``
        for each, and upserts the resulting embedding.

        Args:
            embed_fn: An async callable ``(str) -> list[float]`` that converts
                text to an embedding vector.
            text_field: The entity field to embed (default ``"name"``).
            batch_size: Number of records to process per batch.

        Returns:
            The count of records that were re-indexed.
        """
        if not self.has_vector_support:
            raise NotImplementedError(
                "Cannot reindex: no vector backend configured. "
                "Enable pgvector or provide a vector_sidecar."
            )

        pk = _get_pk_column(self._table)
        reindexed = 0

        if self._pgvector_available and self._embedding_table is not None:
            # Find record IDs that have no embedding row.
            emb_tbl = self._embedding_table
            stmt = (
                sa.select(pk)
                .select_from(
                    self._table.outerjoin(emb_tbl, pk == emb_tbl.c.record_id)
                )
                .where(emb_tbl.c.record_id.is_(None))
                .limit(batch_size)
            )
            try:
                async with AsyncSession(self._engine) as session:
                    result = await session.execute(stmt)
                    missing_ids = [row[0] for row in result.all()]
            except SQLAlchemyError as exc:
                logger.error("reindex scan failed for %s: %s", self._entity.name, type(exc).__name__)
                raise QueryError(
                    entity_name=self._entity.name,
                    operation="reindex_missing_embeddings",
                    detail="Failed to scan for missing embeddings.",
                    cause=exc,
                ) from exc

            for record_id in missing_ids:
                record = await self.find_by_id(str(record_id))
                if record is None:
                    continue
                text = str(record.get(text_field, ""))
                if not text:
                    continue
                embedding = await embed_fn(text)
                await self.upsert_embedding(str(record_id), embedding)
                reindexed += 1
        elif self._vector_sidecar is not None:
            # For sidecar, fetch all records and attempt upsert for each.
            # The sidecar is responsible for deduplication.
            records = await self.find_many(limit=batch_size)
            for record in records:
                pk_val = record.get(pk.name)
                if pk_val is None:
                    continue
                text = str(record.get(text_field, ""))
                if not text:
                    continue
                embedding = await embed_fn(text)
                await self.upsert_embedding(str(pk_val), embedding)
                reindexed += 1

        return reindexed
