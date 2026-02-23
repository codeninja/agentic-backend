"""SQL introspection provider using SQLAlchemy (Postgres/MySQL/SQLite)."""

from __future__ import annotations

import asyncio

from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType
from ninja_core.security import redact_url
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from ninja_introspect.providers.base import IntrospectionProvider, IntrospectionResult

# Default connection timeout in seconds to prevent indefinite hangs on
# unreachable hosts.
_CONNECT_TIMEOUT_SECONDS = 30

# Map SQLAlchemy type names to FieldType
_SQL_TYPE_MAP: dict[str, FieldType] = {
    "INTEGER": FieldType.INTEGER,
    "SMALLINT": FieldType.INTEGER,
    "BIGINT": FieldType.INTEGER,
    "FLOAT": FieldType.FLOAT,
    "REAL": FieldType.FLOAT,
    "DOUBLE": FieldType.FLOAT,
    "DOUBLE_PRECISION": FieldType.FLOAT,
    "NUMERIC": FieldType.FLOAT,
    "DECIMAL": FieldType.FLOAT,
    "VARCHAR": FieldType.STRING,
    "NVARCHAR": FieldType.STRING,
    "CHAR": FieldType.STRING,
    "TEXT": FieldType.TEXT,
    "BOOLEAN": FieldType.BOOLEAN,
    "DATETIME": FieldType.DATETIME,
    "TIMESTAMP": FieldType.DATETIME,
    "DATE": FieldType.DATE,
    "UUID": FieldType.UUID,
    "JSON": FieldType.JSON,
    "JSONB": FieldType.JSON,
    "BLOB": FieldType.BINARY,
    "BYTEA": FieldType.BINARY,
    "ARRAY": FieldType.ARRAY,
}


def _resolve_field_type(sa_type: object) -> FieldType:
    """Map a SQLAlchemy column type to a FieldType."""
    type_name = type(sa_type).__name__.upper()
    if type_name in _SQL_TYPE_MAP:
        return _SQL_TYPE_MAP[type_name]
    # Fallback: try matching by string representation
    type_str = str(sa_type).upper().split("(")[0]
    return _SQL_TYPE_MAP.get(type_str, FieldType.STRING)


def _table_to_pascal(name: str) -> str:
    """Convert a table name like 'user_accounts' to 'UserAccounts'."""
    return "".join(part.capitalize() for part in name.split("_"))


class SQLProvider(IntrospectionProvider):
    """Introspects SQL databases (Postgres, MySQL, SQLite) via SQLAlchemy."""

    async def introspect(
        self,
        connection_string: str,
        *,
        timeout: float = _CONNECT_TIMEOUT_SECONDS,
    ) -> IntrospectionResult:
        """Introspect a SQL database and return discovered entities and relationships.

        Args:
            connection_string: Database connection URI.
            timeout: Maximum seconds to wait for the introspection to complete.
                Defaults to 30 s to prevent indefinite hangs on unreachable
                hosts.

        Raises:
            TimeoutError: If the operation exceeds *timeout* seconds.
        """
        engine = create_async_engine(connection_string, pool_pre_ping=True)
        try:
            return await asyncio.wait_for(
                self._run_introspection(engine),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            safe_url = redact_url(connection_string)
            raise TimeoutError(
                f"Introspection of {safe_url} timed out after {timeout}s. The host may be unreachable."
            ) from None
        except Exception as exc:
            # Re-raise with credentials redacted from the message.
            sanitized_msg = redact_url(str(exc))
            if sanitized_msg != str(exc):
                raise type(exc)(sanitized_msg) from None
            raise
        finally:
            await engine.dispose()

    async def _run_introspection(self, engine: object) -> IntrospectionResult:
        entities: list[EntitySchema] = []
        relationships: list[RelationshipSchema] = []

        async with engine.connect() as conn:  # type: ignore[union-attr]
            table_names: list[str] = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

            for table_name in table_names:
                columns = await conn.run_sync(lambda sync_conn, t=table_name: inspect(sync_conn).get_columns(t))
                pk_constraint = await conn.run_sync(
                    lambda sync_conn, t=table_name: inspect(sync_conn).get_pk_constraint(t)
                )
                unique_constraints = await conn.run_sync(
                    lambda sync_conn, t=table_name: inspect(sync_conn).get_unique_constraints(t)
                )
                indexes = await conn.run_sync(lambda sync_conn, t=table_name: inspect(sync_conn).get_indexes(t))

                pk_columns = set(pk_constraint.get("constrained_columns", []))
                unique_columns: set[str] = set()
                for uc in unique_constraints:
                    if len(uc.get("column_names", [])) == 1:
                        unique_columns.add(uc["column_names"][0])
                indexed_columns: set[str] = set()
                for idx in indexes:
                    if len(idx.get("column_names", [])) == 1:
                        indexed_columns.add(idx["column_names"][0])

                fields: list[FieldSchema] = []
                for col in columns:
                    col_name: str = col["name"]
                    fields.append(
                        FieldSchema(
                            name=col_name,
                            field_type=_resolve_field_type(col["type"]),
                            nullable=col.get("nullable", True),
                            primary_key=col_name in pk_columns,
                            unique=col_name in unique_columns,
                            indexed=col_name in indexed_columns or col_name in pk_columns,
                            default=str(col["default"]) if col.get("default") is not None else None,
                        )
                    )

                entities.append(
                    EntitySchema(
                        name=_table_to_pascal(table_name),
                        storage_engine=StorageEngine.SQL,
                        fields=fields,
                        collection_name=table_name,
                    )
                )

            # Extract foreign key relationships
            for table_name in table_names:
                fks = await conn.run_sync(lambda sync_conn, t=table_name: inspect(sync_conn).get_foreign_keys(t))
                for fk in fks:
                    source_cols = fk.get("constrained_columns", [])
                    target_cols = fk.get("referred_columns", [])
                    referred_table = fk.get("referred_table", "")
                    if source_cols and target_cols and referred_table:
                        relationships.append(
                            RelationshipSchema(
                                name=f"{table_name}_{source_cols[0]}_fk",
                                source_entity=_table_to_pascal(table_name),
                                target_entity=_table_to_pascal(referred_table),
                                relationship_type=RelationshipType.HARD,
                                cardinality=Cardinality.MANY_TO_ONE,
                                source_field=source_cols[0],
                                target_field=target_cols[0],
                            )
                        )

        return IntrospectionResult(entities=entities, relationships=relationships)
