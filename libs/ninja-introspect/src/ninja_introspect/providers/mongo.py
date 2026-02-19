"""MongoDB introspection provider using Motor — infers schema from document samples."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine

from ninja_introspect.providers.base import IntrospectionProvider, IntrospectionResult

# Map Python types (from sampled documents) to FieldType
_PYTHON_TYPE_MAP: dict[type, FieldType] = {
    str: FieldType.STRING,
    int: FieldType.INTEGER,
    float: FieldType.FLOAT,
    bool: FieldType.BOOLEAN,
    datetime: FieldType.DATETIME,
    list: FieldType.ARRAY,
    dict: FieldType.JSON,
    bytes: FieldType.BINARY,
}

DEFAULT_SAMPLE_SIZE = 100


def _infer_field_type(value: Any) -> FieldType:
    """Infer a FieldType from a Python value."""
    if value is None:
        return FieldType.STRING  # Unknown, default to string
    return _PYTHON_TYPE_MAP.get(type(value), FieldType.STRING)


def _collection_to_pascal(name: str) -> str:
    """Convert a collection name to PascalCase entity name."""
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_"))


def _merge_field_info(fields_info: dict[str, dict[str, Any]], doc: dict[str, Any]) -> None:
    """Merge field information from a single document into the accumulated info."""
    for key, value in doc.items():
        if key not in fields_info:
            fields_info[key] = {
                "type": _infer_field_type(value),
                "nullable": value is None,
                "seen": 1,
            }
        else:
            info = fields_info[key]
            info["seen"] += 1
            if value is None:
                info["nullable"] = True
            else:
                # Upgrade type if we see a more specific value
                inferred = _infer_field_type(value)
                if info["type"] == FieldType.STRING and inferred != FieldType.STRING:
                    info["type"] = inferred


class MongoProvider(IntrospectionProvider):
    """Introspects MongoDB databases by sampling documents to infer schema."""

    def __init__(self, sample_size: int = DEFAULT_SAMPLE_SIZE) -> None:
        self.sample_size = sample_size

    async def introspect(self, connection_string: str) -> IntrospectionResult:
        client: AsyncIOMotorClient = AsyncIOMotorClient(connection_string)  # type: ignore[type-arg]
        try:
            db_name = client.get_default_database().name  # type: ignore[union-attr]
            db = client[db_name]

            collection_names: list[str] = await db.list_collection_names()
            # Filter out system collections
            collection_names = [c for c in collection_names if not c.startswith("system.")]

            entities: list[EntitySchema] = []
            for coll_name in sorted(collection_names):
                entity = await self._introspect_collection(db, coll_name)
                if entity is not None:
                    entities.append(entity)

            return IntrospectionResult(entities=entities)
        finally:
            client.close()

    async def _introspect_collection(self, db: Any, collection_name: str) -> EntitySchema | None:
        """Sample documents from a collection and infer its schema."""
        collection = db[collection_name]
        cursor = collection.find().limit(self.sample_size)
        docs = await cursor.to_list(length=self.sample_size)

        if not docs:
            return None

        total_docs = len(docs)
        fields_info: dict[str, dict[str, Any]] = {}
        for doc in docs:
            _merge_field_info(fields_info, doc)

        fields: list[FieldSchema] = []
        for field_name, info in fields_info.items():
            is_id = field_name == "_id"
            fields.append(
                FieldSchema(
                    name=field_name,
                    field_type=info["type"],
                    nullable=info["nullable"] or info["seen"] < total_docs,
                    primary_key=is_id,
                    unique=is_id,
                    indexed=is_id,
                )
            )

        # Sort fields with _id first, then alphabetical
        fields.sort(key=lambda f: (f.name != "_id", f.name))

        return EntitySchema(
            name=_collection_to_pascal(collection_name),
            storage_engine=StorageEngine.MONGO,
            fields=fields,
            collection_name=collection_name,
        )
