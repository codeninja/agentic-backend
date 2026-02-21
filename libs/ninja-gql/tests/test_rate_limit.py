"""Tests for GraphQL rate limiting middleware."""

from __future__ import annotations

import pytest
from ninja_gql.rate_limit import (
    GraphQLRateLimitConfig,
    GraphQLRateLimitMiddleware,
    _client_ip,
    _is_mutation,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------


class TestGraphQLRateLimitConfig:
    """Tests for the rate limit configuration model."""

    def test_defaults(self):
        config = GraphQLRateLimitConfig()
        assert config.enabled is True
        assert config.query_max_requests == 100
        assert config.mutation_max_requests == 50
        assert config.window_seconds == 60
        assert config.per_user_enabled is False
        assert config.graphql_path == "/graphql"

    def test_mutation_stricter_than_query(self):
        config = GraphQLRateLimitConfig()
        assert config.mutation_max_requests < config.query_max_requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for rate limit helper functions."""

    def test_is_mutation_true(self):
        assert _is_mutation({"query": "mutation { createUser { id } }"}) is True

    def test_is_mutation_false(self):
        assert _is_mutation({"query": "query { getUser { id } }"}) is False

    def test_is_mutation_with_whitespace(self):
        assert _is_mutation({"query": "  mutation { deleteUser }"}) is True


# ---------------------------------------------------------------------------
# Middleware integration
# ---------------------------------------------------------------------------


def _make_test_app(config: GraphQLRateLimitConfig | None = None) -> Starlette:
    """Create a test app with rate limiting middleware."""

    async def graphql_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"data": {"ok": True}})

    async def health_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[
            Route("/graphql", graphql_endpoint, methods=["POST"]),
            Route("/health", health_endpoint, methods=["GET"]),
        ],
    )
    app.add_middleware(GraphQLRateLimitMiddleware, config=config)
    return app


class TestGraphQLRateLimitMiddleware:
    """Tests for the rate limiting middleware."""

    def test_within_limit_succeeds(self):
        config = GraphQLRateLimitConfig(query_max_requests=5)
        app = _make_test_app(config)
        client = TestClient(app)

        for _ in range(5):
            response = client.post(
                "/graphql",
                json={"query": "query { getUser { id } }"},
            )
            assert response.status_code == 200

    def test_exceeding_query_limit_returns_429(self):
        config = GraphQLRateLimitConfig(query_max_requests=3, window_seconds=60)
        app = _make_test_app(config)
        client = TestClient(app)

        # Use up the limit
        for _ in range(3):
            response = client.post(
                "/graphql",
                json={"query": "query { getUser { id } }"},
            )
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.post(
            "/graphql",
            json={"query": "query { getUser { id } }"},
        )
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["errors"][0]["message"]

    def test_exceeding_mutation_limit_returns_429(self):
        config = GraphQLRateLimitConfig(mutation_max_requests=2, window_seconds=60)
        app = _make_test_app(config)
        client = TestClient(app)

        # Use up mutation limit
        for _ in range(2):
            response = client.post(
                "/graphql",
                json={"query": "mutation { createUser { id } }"},
            )
            assert response.status_code == 200

        # Next mutation should be rate limited
        response = client.post(
            "/graphql",
            json={"query": "mutation { createUser { id } }"},
        )
        assert response.status_code == 429
        assert "mutation" in response.json()["errors"][0]["message"]

    def test_mutation_limit_independent_of_query_limit(self):
        """Mutations and queries have separate limits."""
        config = GraphQLRateLimitConfig(
            query_max_requests=10,
            mutation_max_requests=2,
            window_seconds=60,
        )
        app = _make_test_app(config)
        client = TestClient(app)

        # Exhaust mutation limit
        for _ in range(2):
            client.post(
                "/graphql",
                json={"query": "mutation { createUser { id } }"},
            )

        # Mutation blocked
        response = client.post(
            "/graphql",
            json={"query": "mutation { createUser { id } }"},
        )
        assert response.status_code == 429

        # Queries still work
        response = client.post(
            "/graphql",
            json={"query": "query { getUser { id } }"},
        )
        assert response.status_code == 200

    def test_non_graphql_path_not_limited(self):
        config = GraphQLRateLimitConfig(query_max_requests=1)
        app = _make_test_app(config)
        client = TestClient(app)

        # Exhaust graphql limit
        client.post("/graphql", json={"query": "query { getUser { id } }"})
        response = client.post("/graphql", json={"query": "query { getUser { id } }"})
        assert response.status_code == 429

        # Non-graphql path not affected
        response = client.get("/health")
        assert response.status_code == 200

    def test_disabled_allows_all(self):
        config = GraphQLRateLimitConfig(enabled=False, query_max_requests=1)
        app = _make_test_app(config)
        client = TestClient(app)

        for _ in range(10):
            response = client.post(
                "/graphql",
                json={"query": "query { getUser { id } }"},
            )
            assert response.status_code == 200

    def test_rate_limit_error_format(self):
        """Rate limit error should be a valid GraphQL error response."""
        config = GraphQLRateLimitConfig(query_max_requests=1)
        app = _make_test_app(config)
        client = TestClient(app)

        client.post("/graphql", json={"query": "query { getUser { id } }"})
        response = client.post("/graphql", json={"query": "query { getUser { id } }"})

        data = response.json()
        assert "errors" in data
        assert isinstance(data["errors"], list)
        assert "message" in data["errors"][0]
