"""Standard CRUD resolver implementations.

Each resolver delegates to a ``ninja_persistence.Repository`` instance looked up
from a registry function supplied at schema-build time.
"""

from typing import Any, Callable, Optional

import strawberry
from ninja_core.schema.entity import EntitySchema
from ninja_persistence.protocols import Repository


def make_get_resolver(
    entity: EntitySchema,
    gql_type: type,
    repo_getter: Callable[[str], Repository[Any]],
) -> Callable:
    """Return an async resolver: ``get_{entity}(id) -> GqlType | None``."""

    async def resolver(id: str) -> Optional[gql_type]:  # type: ignore[valid-type]
        repo = repo_getter(entity.name)
        row = await repo.find_by_id(id)
        if row is None:
            return None
        return gql_type(**row)

    resolver.__name__ = f"get_{_snake(entity.name)}"
    return resolver


def make_list_resolver(
    entity: EntitySchema,
    gql_type: type,
    repo_getter: Callable[[str], Repository[Any]],
) -> Callable:
    """Return an async resolver: ``list_{entity}(limit, offset) -> [GqlType]``."""

    async def resolver(limit: int = 100, offset: int = 0) -> list[gql_type]:  # type: ignore[valid-type]
        repo = repo_getter(entity.name)
        rows = await repo.find_many(limit=limit)
        return [gql_type(**r) for r in rows[offset:]]

    resolver.__name__ = f"list_{_snake(entity.name)}"
    return resolver


def make_create_resolver(
    entity: EntitySchema,
    gql_type: type,
    repo_getter: Callable[[str], Repository[Any]],
) -> Callable:
    """Return an async resolver: ``create_{entity}(input) -> GqlType``."""

    async def resolver(input: strawberry.scalars.JSON) -> gql_type:  # type: ignore[valid-type]
        repo = repo_getter(entity.name)
        row = await repo.create(input)
        return gql_type(**row)

    resolver.__name__ = f"create_{_snake(entity.name)}"
    return resolver


def make_update_resolver(
    entity: EntitySchema,
    gql_type: type,
    repo_getter: Callable[[str], Repository[Any]],
) -> Callable:
    """Return an async resolver: ``update_{entity}(id, patch) -> GqlType | None``."""

    async def resolver(id: str, patch: strawberry.scalars.JSON) -> Optional[gql_type]:  # type: ignore[valid-type]
        repo = repo_getter(entity.name)
        row = await repo.update(id, patch)
        if row is None:
            return None
        return gql_type(**row)

    resolver.__name__ = f"update_{_snake(entity.name)}"
    return resolver


def make_delete_resolver(
    entity: EntitySchema,
    repo_getter: Callable[[str], Repository[Any]],
) -> Callable:
    """Return an async resolver: ``delete_{entity}(id) -> bool``."""

    async def resolver(id: str) -> bool:
        repo = repo_getter(entity.name)
        return await repo.delete(id)

    resolver.__name__ = f"delete_{_snake(entity.name)}"
    return resolver


def _snake(name: str) -> str:
    """PascalCase → snake_case."""
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
