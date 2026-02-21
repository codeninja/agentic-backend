"""SQLAlchemy async adapter implementing the Repository protocol."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from ninja_core.schema.entity import EntitySchema, FieldType
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
        pk = _get_pk_column(self._table)
        stmt = self._table.select().where(pk == id)
        async with AsyncSession(self._engine) as session:
            result = await session.execute(stmt)
            row = result.mappings().first()
            return dict(row) if row else None

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        stmt = self._table.select().limit(limit)
        if filters:
            for col_name, value in filters.items():
                if col_name in self._table.c:
                    stmt = stmt.where(self._table.c[col_name] == value)
        async with AsyncSession(self._engine) as session:
            result = await session.execute(stmt)
            return [dict(row) for row in result.mappings().all()]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        stmt = self._table.insert().values(**data)
        async with AsyncSession(self._engine) as session:
            await session.execute(stmt)
            await session.commit()
        return data

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        pk = _get_pk_column(self._table)
        stmt = self._table.update().where(pk == id).values(**patch)
        async with AsyncSession(self._engine) as session:
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount == 0:
                return None
        return await self.find_by_id(id)

    async def delete(self, id: str) -> bool:
        pk = _get_pk_column(self._table)
        stmt = self._table.delete().where(pk == id)
        async with AsyncSession(self._engine) as session:
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

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
