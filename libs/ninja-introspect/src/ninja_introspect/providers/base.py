"""Abstract base for database introspection providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ninja_core.schema.entity import EntitySchema
from ninja_core.schema.relationship import RelationshipSchema


@dataclass
class IntrospectionResult:
    """Result from a single provider's introspection run."""

    entities: list[EntitySchema] = field(default_factory=list)
    relationships: list[RelationshipSchema] = field(default_factory=list)


class IntrospectionProvider(ABC):
    """Protocol for database introspection providers.

    Each provider connects to a specific database type, reads its schema,
    and produces EntitySchema + RelationshipSchema objects.
    """

    @abstractmethod
    async def introspect(self, connection_string: str) -> IntrospectionResult:
        """Connect to the database and extract schema information.

        Args:
            connection_string: Database connection URI.

        Returns:
            IntrospectionResult containing discovered entities and relationships.
        """
