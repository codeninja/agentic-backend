"""Neo4j graph introspection provider."""

from __future__ import annotations

from typing import Any

from neo4j import AsyncGraphDatabase
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType

from ninja_introspect.providers.base import IntrospectionProvider, IntrospectionResult

# Map Neo4j type names to FieldType
_NEO4J_TYPE_MAP: dict[str, FieldType] = {
    "Long": FieldType.INTEGER,
    "Double": FieldType.FLOAT,
    "String": FieldType.STRING,
    "Boolean": FieldType.BOOLEAN,
    "Date": FieldType.DATE,
    "DateTime": FieldType.DATETIME,
    "LocalDateTime": FieldType.DATETIME,
    "Point": FieldType.JSON,
    "List": FieldType.ARRAY,
}


def _neo4j_type_to_field_type(neo4j_type: str) -> FieldType:
    """Map a Neo4j property type string to a FieldType."""
    return _NEO4J_TYPE_MAP.get(neo4j_type, FieldType.STRING)


def _python_type_to_field_type(value: Any) -> FieldType:
    """Infer FieldType from a Python value returned by Neo4j."""
    if isinstance(value, bool):
        return FieldType.BOOLEAN
    if isinstance(value, int):
        return FieldType.INTEGER
    if isinstance(value, float):
        return FieldType.FLOAT
    if isinstance(value, list):
        return FieldType.ARRAY
    return FieldType.STRING


DEFAULT_SAMPLE_SIZE = 100


class GraphProvider(IntrospectionProvider):
    """Introspects Neo4j graph databases — reads node labels, relationship types, and properties."""

    def __init__(self, sample_size: int = DEFAULT_SAMPLE_SIZE) -> None:
        self.sample_size = sample_size

    async def introspect(self, connection_string: str) -> IntrospectionResult:
        driver = AsyncGraphDatabase.driver(connection_string)
        try:
            return await self._run_introspection(driver)
        finally:
            await driver.close()

    async def _run_introspection(self, driver: Any) -> IntrospectionResult:
        entities: list[EntitySchema] = []
        relationships: list[RelationshipSchema] = []

        async with driver.session() as session:
            # Get all node labels
            labels = await self._get_node_labels(session)

            for label in sorted(labels):
                entity = await self._introspect_label(session, label)
                if entity is not None:
                    entities.append(entity)

            # Get relationship types
            rel_types = await self._get_relationship_types(session)
            for rel_type_info in rel_types:
                relationships.append(rel_type_info)

        return IntrospectionResult(entities=entities, relationships=relationships)

    async def _get_node_labels(self, session: Any) -> list[str]:
        result = await session.run("CALL db.labels()")
        records = [record async for record in result]
        return [record["label"] for record in records]

    async def _get_relationship_types(self, session: Any) -> list[RelationshipSchema]:
        """Discover relationship types by sampling the graph."""
        result = await session.run(
            "MATCH (a)-[r]->(b) "
            "WITH type(r) AS rel_type, labels(a)[0] AS src, labels(b)[0] AS tgt "
            "RETURN DISTINCT rel_type, src, tgt"
        )
        relationships: list[RelationshipSchema] = []
        async for record in result:
            rel_type = record["rel_type"]
            src = record["src"]
            tgt = record["tgt"]
            relationships.append(
                RelationshipSchema(
                    name=f"{src}_{rel_type}_{tgt}".lower(),
                    source_entity=src,
                    target_entity=tgt,
                    relationship_type=RelationshipType.GRAPH,
                    cardinality=Cardinality.MANY_TO_MANY,
                    edge_label=rel_type,
                )
            )
        return relationships

    async def _introspect_label(self, session: Any, label: str) -> EntitySchema | None:
        """Sample nodes with a given label and infer properties."""
        result = await session.run(
            f"MATCH (n:`{label}`) RETURN properties(n) AS props LIMIT $limit",
            limit=self.sample_size,
        )
        records = [record async for record in result]
        if not records:
            return None

        # Merge properties across sampled nodes
        total = len(records)
        props_info: dict[str, dict[str, Any]] = {}
        for record in records:
            props = record["props"]
            for key, value in props.items():
                if key not in props_info:
                    props_info[key] = {
                        "type": _python_type_to_field_type(value),
                        "seen": 1,
                    }
                else:
                    props_info[key]["seen"] += 1

        fields: list[FieldSchema] = []
        for prop_name, info in sorted(props_info.items()):
            fields.append(
                FieldSchema(
                    name=prop_name,
                    field_type=info["type"],
                    nullable=info["seen"] < total,
                )
            )

        if not fields:
            return None

        return EntitySchema(
            name=label,
            storage_engine=StorageEngine.GRAPH,
            fields=fields,
        )
