"""Introspection engine — orchestrates providers and merges results into an AgenticSchema."""

from __future__ import annotations

from ninja_core.schema.entity import EntitySchema
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import RelationshipSchema

from ninja_introspect.providers.base import IntrospectionProvider, IntrospectionResult
from ninja_introspect.providers.graph import GraphProvider
from ninja_introspect.providers.mongo import MongoProvider
from ninja_introspect.providers.sql import SQLProvider
from ninja_introspect.providers.vector import VectorProvider

# Map URL schemes to provider classes
_SCHEME_PROVIDER_MAP: dict[str, type[IntrospectionProvider]] = {
    "postgresql": SQLProvider,
    "postgresql+asyncpg": SQLProvider,
    "postgres": SQLProvider,
    "mysql": SQLProvider,
    "mysql+aiomysql": SQLProvider,
    "sqlite": SQLProvider,
    "sqlite+aiosqlite": SQLProvider,
    "mongodb": SQLProvider,  # Overridden below
    "mongodb+srv": SQLProvider,  # Overridden below
    "bolt": GraphProvider,
    "neo4j": GraphProvider,
    "neo4j+s": GraphProvider,
    "neo4j+ssc": GraphProvider,
}

# Mongo schemes override the default
_SCHEME_PROVIDER_MAP["mongodb"] = MongoProvider  # type: ignore[assignment]
_SCHEME_PROVIDER_MAP["mongodb+srv"] = MongoProvider  # type: ignore[assignment]


def _detect_provider(connection_string: str) -> IntrospectionProvider:
    """Detect the correct provider based on the connection string scheme."""
    scheme = connection_string.split("://")[0].lower() if "://" in connection_string else ""

    provider_class = _SCHEME_PROVIDER_MAP.get(scheme)
    if provider_class is not None:
        return provider_class()

    # Heuristic fallbacks
    if connection_string.startswith("http://") or connection_string.startswith("https://"):
        return VectorProvider()

    # If it looks like a path (for Chroma persist dir)
    if "/" in connection_string and "://" not in connection_string:
        return VectorProvider()

    raise ValueError(f"Cannot detect provider for connection string scheme: {scheme!r}")


class IntrospectionEngine:
    """Orchestrates multiple introspection providers and merges their results.

    Usage::

        engine = IntrospectionEngine(project_name="my-project")
        schema = await engine.run([
            "sqlite+aiosqlite:///path/to/db.sqlite",
            "mongodb://localhost:27017/mydb",
        ])
    """

    def __init__(self, project_name: str = "untitled") -> None:
        self.project_name = project_name

    async def run(
        self,
        connection_strings: list[str],
        *,
        providers: dict[str, IntrospectionProvider] | None = None,
    ) -> AgenticSchema:
        """Run introspection across all connection strings and merge results.

        Args:
            connection_strings: List of database connection URIs.
            providers: Optional mapping of connection string → provider override.

        Returns:
            A merged AgenticSchema containing entities and relationships from all sources.
        """
        all_entities: list[EntitySchema] = []
        all_relationships: list[RelationshipSchema] = []

        for conn_str in connection_strings:
            if providers and conn_str in providers:
                provider = providers[conn_str]
            else:
                provider = _detect_provider(conn_str)

            result: IntrospectionResult = await provider.introspect(conn_str)
            all_entities.extend(result.entities)
            all_relationships.extend(result.relationships)

        return AgenticSchema(
            project_name=self.project_name,
            entities=all_entities,
            relationships=all_relationships,
        )
