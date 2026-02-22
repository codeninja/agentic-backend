"""SQLAlchemy async adapter implementing the Repository protocol."""

from __future__ import annotations

import logging
from typing import Any

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


def _get_pk_column(table: sa.Table) -> sa.Column:
    """Return the primary key column of a table."""
    pk_cols = list(table.primary_key.columns)
    if not pk_cols:
        raise ValueError(f"Table '{table.name}' has no primary key column.")
    return pk_cols[0]


class SQLAdapter:
    """Async SQL adapter backed by SQLAlchemy.

    Implements the Repository protocol for relational databases.
    """

    def __init__(self, engine: AsyncEngine, entity: EntitySchema) -> None:
        self._engine = engine
        self._entity = entity
        self._metadata = sa.MetaData()
        self._table = _build_table(entity, self._metadata)

    @property
    def table(self) -> sa.Table:
        return self._table

    async def ensure_table(self) -> None:
        """Create the table if it does not exist."""
        async with self._engine.begin() as conn:
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

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Semantic search is not natively supported in SQL.

        Raises ``NotImplementedError`` directing callers to configure a vector
        sidecar (Chroma/Milvus) for the entity.
        """
        raise NotImplementedError(
            "Semantic search not available for SQL adapter. "
            "Configure a vector sidecar (Chroma/Milvus) for this entity to enable semantic search."
        )

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Embedding storage is not natively supported in SQL.

        Raises ``NotImplementedError`` directing callers to configure a vector
        sidecar (Chroma/Milvus) for the entity.
        """
        raise NotImplementedError(
            "Embedding storage not available for SQL adapter. "
            "Configure a vector sidecar (Chroma/Milvus) for this entity to manage embeddings."
        )
