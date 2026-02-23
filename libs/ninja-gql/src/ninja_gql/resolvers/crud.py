"""Standard CRUD resolver implementations.

Each resolver delegates to a ``ninja_persistence.Repository`` instance looked up
from a registry function supplied at schema-build time.  Create and update
mutations validate their JSON input against the ASD entity schema before
passing data to the repository.

Mutation resolvers enforce authorization via the ``ninja_auth`` context-var
bridge: the caller must have ``write:<domain>.<entity>`` (create/update) or
``delete:<domain>.<entity>`` permission for the target entity.
"""

from typing import Any, Callable, Optional

import strawberry
from ninja_core.schema.entity import EntitySchema
from ninja_persistence.protocols import Repository

from ninja_gql.validation import (
    InputValidationError,
    validate_create_input,
    validate_update_input,
)


def _check_mutation_auth(action: str, domain: str | None, entity_name: str) -> None:
    """Verify the current user has permission to mutate *entity_name*.

    When a *domain* is provided the check uses RBAC domain access
    (``action:domain.entity``).  When no domain mapping exists the check
    falls back to requiring ``action:entity_name`` as a direct permission.

    Raises ``PermissionError`` propagated by ``ninja_auth``.
    """
    from ninja_auth.agent_context import require_domain_access, require_permission

    if domain is not None:
        require_domain_access(action, domain, entity=entity_name)
    else:
        require_permission(f"{action}:{entity_name}")


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
    domain: str | None = None,
) -> Callable:
    """Return an async resolver: ``create_{entity}(input) -> GqlType``.

    Validates the JSON input against the ASD entity field definitions
    before delegating to the repository.  Unknown fields are rejected
    (mass-assignment protection) and type/constraint checks are enforced.

    Authorization: requires ``write:<domain>.<entity>`` permission.
    """

    async def resolver(input: strawberry.scalars.JSON) -> gql_type:  # type: ignore[valid-type]
        _check_mutation_auth("write", domain, entity.name)
        try:
            validated = validate_create_input(entity, input)
        except InputValidationError as exc:
            raise ValueError("; ".join(exc.errors)) from exc
        repo = repo_getter(entity.name)
        row = await repo.create(validated)
        return gql_type(**row)

    resolver.__name__ = f"create_{_snake(entity.name)}"
    return resolver


def make_update_resolver(
    entity: EntitySchema,
    gql_type: type,
    repo_getter: Callable[[str], Repository[Any]],
    domain: str | None = None,
) -> Callable:
    """Return an async resolver: ``update_{entity}(id, patch) -> GqlType | None``.

    Validates the JSON patch against the ASD entity field definitions
    before delegating to the repository.  Unknown fields and primary-key
    modifications are rejected.

    Authorization: requires ``write:<domain>.<entity>`` permission.
    """

    async def resolver(id: str, patch: strawberry.scalars.JSON) -> Optional[gql_type]:  # type: ignore[valid-type]
        _check_mutation_auth("write", domain, entity.name)
        try:
            validated = validate_update_input(entity, patch)
        except InputValidationError as exc:
            raise ValueError("; ".join(exc.errors)) from exc
        repo = repo_getter(entity.name)
        row = await repo.update(id, validated)
        if row is None:
            return None
        return gql_type(**row)

    resolver.__name__ = f"update_{_snake(entity.name)}"
    return resolver


def make_delete_resolver(
    entity: EntitySchema,
    repo_getter: Callable[[str], Repository[Any]],
    domain: str | None = None,
) -> Callable:
    """Return an async resolver: ``delete_{entity}(id) -> bool``.

    Authorization: requires ``delete:<domain>.<entity>`` permission.
    """

    async def resolver(id: str) -> bool:
        _check_mutation_auth("delete", domain, entity.name)
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
