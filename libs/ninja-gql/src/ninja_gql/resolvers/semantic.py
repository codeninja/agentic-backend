"""Semantic search resolvers.

Expose ``search_{entity}(query: str, limit: int)`` for entities that have
embeddable fields configured in the ASD.
"""

from typing import Any, Callable

from ninja_core.schema.entity import EntitySchema
from ninja_persistence.protocols import Repository


def make_search_resolver(
    entity: EntitySchema,
    gql_type: type,
    repo_getter: Callable[[str], Repository[Any]],
) -> Callable:
    """Return an async resolver: ``search_{entity}(query, limit) -> [GqlType]``."""

    async def resolver(query: str, limit: int = 10) -> list[gql_type]:  # type: ignore[valid-type]
        repo = repo_getter(entity.name)
        rows = await repo.search_semantic(query, limit=limit)
        return [gql_type(**r) for r in rows]

    resolver.__name__ = f"search_{_snake(entity.name)}"
    return resolver


def _snake(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
