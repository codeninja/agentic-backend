"""Repository protocol — engine-agnostic persistence interface."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T", covariant=True)


@runtime_checkable
class Repository(Protocol[T]):
    """Unified persistence interface for all storage engines.

    Every adapter (SQL, Mongo, Graph, Vector) implements this protocol so that
    Data Agents can perform CRUD and semantic search without knowing the backend.
    """

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        """Retrieve a single record by primary key."""
        ...

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve multiple records matching the given filters."""
        ...

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new record and return the created entity."""
        ...

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Apply a partial update to an existing record."""
        ...

    async def delete(self, id: str) -> bool:
        """Delete a record by primary key. Returns True if deleted."""
        ...

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Perform semantic (vector similarity) search."""
        ...

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        """Insert or update the embedding vector for a record."""
        ...
