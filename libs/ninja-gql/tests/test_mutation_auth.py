"""Tests for authorization checks on generated GraphQL mutations."""

from __future__ import annotations

from typing import Any

import pytest
from ninja_auth.agent_context import clear_user_context, set_user_context
from ninja_auth.context import ANONYMOUS_USER, UserContext
from ninja_core.schema.project import AgenticSchema
from ninja_gql.schema import build_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(**kwargs: Any) -> UserContext:
    defaults: dict[str, Any] = {"user_id": "u1", "provider": "test"}
    defaults.update(kwargs)
    return UserContext(**defaults)


class MockRepo:
    """Minimal repo that satisfies all CRUD operations."""

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        return {"id": id, "name": "Alice", "email": "a@test.com"}

    async def find_many(self, filters=None, limit=100) -> list[dict[str, Any]]:
        return []

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        return {**data, "id": "new-id"}

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        return {"id": id, "name": patch.get("name", "Alice"), "email": "a@test.com"}

    async def delete(self, id: str) -> bool:
        return True

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return []

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        pass


def _build(asd: AgenticSchema):
    repos = {e.name: MockRepo() for e in asd.entities}
    return build_schema(asd, repo_getter=lambda name: repos[name])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_user_context():
    """Ensure each test starts with anonymous context."""
    token = set_user_context(ANONYMOUS_USER)
    yield
    clear_user_context(token)


# ---------------------------------------------------------------------------
# Tests — unauthenticated callers are rejected
# ---------------------------------------------------------------------------

class TestMutationAuthRejectsAnonymous:
    """Mutations must fail when no authenticated user context is set."""

    async def test_create_rejects_anonymous(self, sample_asd: AgenticSchema):
        schema = _build(sample_asd)

        result = await schema.execute(
            'mutation { createCustomer(input: {name: "X", email: "x@t.com"}) { id } }'
        )
        assert result.errors is not None
        assert any("permission" in str(e).lower() or "authenticated" in str(e).lower() for e in result.errors)

    async def test_update_rejects_anonymous(self, sample_asd: AgenticSchema):
        schema = _build(sample_asd)

        result = await schema.execute(
            'mutation { updateCustomer(id: "abc", patch: {name: "Y"}) { id } }'
        )
        assert result.errors is not None
        assert any("permission" in str(e).lower() or "authenticated" in str(e).lower() for e in result.errors)

    async def test_delete_rejects_anonymous(self, sample_asd: AgenticSchema):
        schema = _build(sample_asd)

        result = await schema.execute('mutation { deleteCustomer(id: "abc") }')
        assert result.errors is not None
        assert any("permission" in str(e).lower() or "authenticated" in str(e).lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Tests — authenticated callers with correct permissions succeed
# ---------------------------------------------------------------------------

class TestMutationAuthAllowsAuthorized:
    """Mutations succeed when the user has the required write/delete permission."""

    async def test_create_with_write_permission(self, sample_asd: AgenticSchema):
        user = _make_user(permissions=["write:Sales.Customer"])
        set_user_context(user)
        schema = _build(sample_asd)

        result = await schema.execute(
            'mutation { createCustomer(input: {name: "Z", email: "z@t.com"}) { id name } }'
        )
        assert result.errors is None
        assert result.data["createCustomer"]["name"] == "Z"

    async def test_update_with_write_permission(self, sample_asd: AgenticSchema):
        user = _make_user(permissions=["write:Sales.Customer"])
        set_user_context(user)
        schema = _build(sample_asd)

        result = await schema.execute(
            'mutation { updateCustomer(id: "abc", patch: {name: "Updated"}) { id name } }'
        )
        assert result.errors is None
        assert result.data["updateCustomer"]["name"] == "Updated"

    async def test_delete_with_delete_permission(self, sample_asd: AgenticSchema):
        user = _make_user(permissions=["delete:Sales.Customer"])
        set_user_context(user)
        schema = _build(sample_asd)

        result = await schema.execute('mutation { deleteCustomer(id: "abc") }')
        assert result.errors is None
        assert result.data["deleteCustomer"] is True

    async def test_wildcard_permission_grants_access(self, sample_asd: AgenticSchema):
        user = _make_user(permissions=["write:*"])
        set_user_context(user)
        schema = _build(sample_asd)

        result = await schema.execute(
            'mutation { createOrder(input: {customer_id: "c1", total: 9.99, status: "new"}) { id } }'
        )
        assert result.errors is None


# ---------------------------------------------------------------------------
# Tests — authenticated but wrong permissions are rejected
# ---------------------------------------------------------------------------

class TestMutationAuthRejectsInsufficient:
    """Mutations fail when the user is authenticated but lacks the needed permission."""

    async def test_read_permission_not_enough_for_create(self, sample_asd: AgenticSchema):
        user = _make_user(permissions=["read:Sales.Customer"])
        set_user_context(user)
        schema = _build(sample_asd)

        result = await schema.execute(
            'mutation { createCustomer(input: {name: "X", email: "x@t.com"}) { id } }'
        )
        assert result.errors is not None

    async def test_write_on_wrong_entity_rejected(self, sample_asd: AgenticSchema):
        user = _make_user(permissions=["write:Sales.Order"])
        set_user_context(user)
        schema = _build(sample_asd)

        result = await schema.execute(
            'mutation { createCustomer(input: {name: "X", email: "x@t.com"}) { id } }'
        )
        assert result.errors is not None

    async def test_delete_needs_delete_not_write(self, sample_asd: AgenticSchema):
        user = _make_user(permissions=["write:Sales.Customer"])
        set_user_context(user)
        schema = _build(sample_asd)

        result = await schema.execute('mutation { deleteCustomer(id: "abc") }')
        assert result.errors is not None


# ---------------------------------------------------------------------------
# Tests — queries remain unaffected (no auth required)
# ---------------------------------------------------------------------------

class TestQueriesUnaffected:
    """Read queries should still work without authentication."""

    async def test_get_query_works_anonymous(self, sample_asd: AgenticSchema):
        schema = _build(sample_asd)

        result = await schema.execute('{ getCustomer(id: "abc") { id name } }')
        assert result.errors is None

    async def test_list_query_works_anonymous(self, sample_asd: AgenticSchema):
        schema = _build(sample_asd)

        result = await schema.execute("{ listCustomer { id name } }")
        assert result.errors is None
