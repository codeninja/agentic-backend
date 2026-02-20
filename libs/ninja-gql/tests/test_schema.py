"""Tests for schema assembly and SDL generation."""

from __future__ import annotations

from typing import Any

import strawberry
from ninja_core.schema.project import AgenticSchema
from ninja_gql.schema import build_schema, build_schema_sdl


class TestBuildSchema:
    def test_returns_strawberry_schema(self, sample_asd: AgenticSchema):
        schema = build_schema(sample_asd)
        assert isinstance(schema, strawberry.Schema)

    def test_schema_has_query_and_mutation(self, sample_asd: AgenticSchema):
        schema = build_schema(sample_asd)
        sdl = str(schema)

        assert "Query" in sdl
        assert "Mutation" in sdl

    def test_get_queries_generated(self, sample_asd: AgenticSchema):
        sdl = build_schema_sdl(sample_asd)

        assert "getCustomer" in sdl
        assert "getOrder" in sdl
        assert "getProduct" in sdl

    def test_list_queries_generated(self, sample_asd: AgenticSchema):
        sdl = build_schema_sdl(sample_asd)

        assert "listCustomer" in sdl
        assert "listOrder" in sdl
        assert "listProduct" in sdl

    def test_search_query_only_for_embeddable(self, sample_asd: AgenticSchema):
        sdl = build_schema_sdl(sample_asd)

        # Product has embedding, Customer/Order do not
        assert "searchProduct" in sdl
        assert "searchCustomer" not in sdl
        assert "searchOrder" not in sdl

    def test_mutations_generated(self, sample_asd: AgenticSchema):
        sdl = build_schema_sdl(sample_asd)

        assert "createCustomer" in sdl
        assert "updateCustomer" in sdl
        assert "deleteCustomer" in sdl
        assert "createOrder" in sdl
        assert "deleteProduct" in sdl

    def test_agent_query_generated(self, sample_asd: AgenticSchema):
        sdl = build_schema_sdl(sample_asd)

        assert "askSales" in sdl
        assert "askCatalog" in sdl


class TestSchemaExecution:
    async def test_get_query_returns_none_without_repo(self, sample_asd: AgenticSchema):
        """Calling a resolver without a real repo raises RuntimeError."""
        schema = build_schema(sample_asd)

        result = await schema.execute('{ getCustomer(id: "abc") { id name } }')
        # Should error because no repo is configured
        assert result.errors is not None
        assert len(result.errors) > 0

    async def test_get_query_resolves_with_mock_repo(self, sample_asd: AgenticSchema):
        """With a mock repo, queries resolve correctly."""
        import uuid

        uid = str(uuid.uuid4())

        class MockRepo:
            async def find_by_id(self, id: str) -> dict[str, Any] | None:
                return {"id": uid, "name": "Alice", "email": "alice@test.com"}

            async def find_many(self, filters=None, limit=100) -> list[dict[str, Any]]:
                return [{"id": uid, "name": "Alice", "email": "alice@test.com"}]

            async def create(self, data: dict[str, Any]) -> dict[str, Any]:
                return {**data, "id": uid}

            async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
                return {"id": id, "name": patch.get("name", "Alice"), "email": "alice@test.com"}

            async def delete(self, id: str) -> bool:
                return True

            async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
                return []

            async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
                pass

        repos: dict[str, Any] = {
            "Customer": MockRepo(),
            "Order": MockRepo(),
            "Product": MockRepo(),
        }
        schema = build_schema(sample_asd, repo_getter=lambda name: repos[name])

        result = await schema.execute(f'{{ getCustomer(id: "{uid}") {{ id name email }} }}')
        assert result.errors is None
        assert result.data["getCustomer"]["name"] == "Alice"

    async def test_list_query_resolves(self, sample_asd: AgenticSchema):
        uid = "test-id-123"

        class MockRepo:
            async def find_by_id(self, id: str) -> dict[str, Any] | None:
                return None

            async def find_many(self, filters=None, limit=100) -> list[dict[str, Any]]:
                return [
                    {"id": uid, "name": "Bob", "email": "bob@test.com"},
                    {"id": "id-2", "name": "Carol", "email": "carol@test.com"},
                ]

            async def create(self, data):
                return data

            async def update(self, id, patch):
                return None

            async def delete(self, id):
                return False

            async def search_semantic(self, query, limit=10):
                return []

            async def upsert_embedding(self, id, embedding):
                pass

        repos = {"Customer": MockRepo(), "Order": MockRepo(), "Product": MockRepo()}
        schema = build_schema(sample_asd, repo_getter=lambda name: repos[name])

        result = await schema.execute("{ listCustomer { id name } }")
        assert result.errors is None
        assert len(result.data["listCustomer"]) == 2

    async def test_mutation_create_resolves(self, sample_asd: AgenticSchema):
        created: list[dict] = []

        class MockRepo:
            async def find_by_id(self, id):
                return None

            async def find_many(self, filters=None, limit=100):
                return []

            async def create(self, data: dict[str, Any]) -> dict[str, Any]:
                created.append(data)
                return {**data, "id": "new-id"}

            async def update(self, id, patch):
                return None

            async def delete(self, id):
                return True

            async def search_semantic(self, query, limit=10):
                return []

            async def upsert_embedding(self, id, embedding):
                pass

        repos = {"Customer": MockRepo(), "Order": MockRepo(), "Product": MockRepo()}
        schema = build_schema(sample_asd, repo_getter=lambda name: repos[name])

        result = await schema.execute(
            'mutation { createCustomer(input: {name: "Dave", email: "d@test.com"}) { id name } }'
        )
        assert result.errors is None
        assert result.data["createCustomer"]["name"] == "Dave"

    async def test_mutation_delete_resolves(self, sample_asd: AgenticSchema):
        class MockRepo:
            async def find_by_id(self, id):
                return None

            async def find_many(self, filters=None, limit=100):
                return []

            async def create(self, data):
                return data

            async def update(self, id, patch):
                return None

            async def delete(self, id: str) -> bool:
                return True

            async def search_semantic(self, query, limit=10):
                return []

            async def upsert_embedding(self, id, embedding):
                pass

        repos = {"Customer": MockRepo(), "Order": MockRepo(), "Product": MockRepo()}
        schema = build_schema(sample_asd, repo_getter=lambda name: repos[name])

        result = await schema.execute('mutation { deleteCustomer(id: "abc") }')
        assert result.errors is None
        assert result.data["deleteCustomer"] is True

    async def test_search_query_resolves(self, sample_asd: AgenticSchema):
        class MockRepo:
            async def find_by_id(self, id):
                return None

            async def find_many(self, filters=None, limit=100):
                return []

            async def create(self, data):
                return data

            async def update(self, id, patch):
                return None

            async def delete(self, id):
                return False

            async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
                return [{"id": "p1", "name": "Red Shoes", "price": 59.99, "description": "Bright red shoes"}]

            async def upsert_embedding(self, id, embedding):
                pass

        repos = {"Customer": MockRepo(), "Order": MockRepo(), "Product": MockRepo()}
        schema = build_schema(sample_asd, repo_getter=lambda name: repos[name])

        result = await schema.execute('{ searchProduct(query: "red shoes") { id name price } }')
        assert result.errors is None
        assert result.data["searchProduct"][0]["name"] == "Red Shoes"

    async def test_agent_query_without_router(self, sample_asd: AgenticSchema):
        schema = build_schema(sample_asd)

        result = await schema.execute('{ askSales(query: "top customers") }')
        assert result.errors is None
        data = result.data["askSales"]
        assert "error" in str(data) or "Agent routing not configured" in str(data)
