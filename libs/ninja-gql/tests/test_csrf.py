"""Tests for CSRF protection middleware."""

from __future__ import annotations

from ninja_gql.csrf import (
    CSRFConfig,
    CSRFMiddleware,
    _is_mutation_request,
    generate_csrf_token,
    verify_csrf_token,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


class TestCSRFTokens:
    """Tests for CSRF token generation and verification."""

    def test_generate_token_format(self):
        token = generate_csrf_token("secret123")
        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2

    def test_verify_valid_token(self):
        secret = "my-secret"
        token = generate_csrf_token(secret)
        assert verify_csrf_token(token, secret) is True

    def test_verify_invalid_token(self):
        assert verify_csrf_token("invalid-token", "secret") is False

    def test_verify_tampered_token(self):
        secret = "my-secret"
        token = generate_csrf_token(secret)
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert verify_csrf_token(tampered, secret) is False

    def test_verify_wrong_secret(self):
        token = generate_csrf_token("correct-secret")
        assert verify_csrf_token(token, "wrong-secret") is False

    def test_tokens_are_unique(self):
        tokens = {generate_csrf_token("secret") for _ in range(10)}
        assert len(tokens) == 10


# ---------------------------------------------------------------------------
# Mutation detection
# ---------------------------------------------------------------------------


class TestMutationDetection:
    """Tests for the _is_mutation_request helper."""

    def test_mutation_detected(self):
        assert _is_mutation_request({"query": "mutation { createUser(input: {}) { id } }"}) is True

    def test_query_not_mutation(self):
        assert _is_mutation_request({"query": "query { getUser(id: 1) { name } }"}) is False

    def test_mutation_with_whitespace(self):
        assert _is_mutation_request({"query": "  mutation CreateUser { createUser { id } }"}) is True

    def test_empty_query(self):
        assert _is_mutation_request({"query": ""}) is False

    def test_missing_query(self):
        assert _is_mutation_request({}) is False


# ---------------------------------------------------------------------------
# CSRFConfig
# ---------------------------------------------------------------------------


class TestCSRFConfig:
    """Tests for the CSRFConfig model."""

    def test_defaults(self):
        config = CSRFConfig()
        assert config.enabled is True
        assert config.header_name == "X-Requested-With"
        assert config.cookie_samesite == "Lax"

    def test_custom_header(self):
        config = CSRFConfig(header_name="X-CSRF-Token")
        assert config.header_name == "X-CSRF-Token"


# ---------------------------------------------------------------------------
# Middleware integration
# ---------------------------------------------------------------------------


def _make_test_app(config: CSRFConfig | None = None) -> Starlette:
    """Create a test Starlette app with CSRF middleware."""

    async def graphql_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"data": {"ok": True}})

    app = Starlette(
        routes=[Route("/graphql", graphql_endpoint, methods=["POST", "GET"])],
    )
    app.add_middleware(CSRFMiddleware, config=config)
    return app


class TestCSRFMiddleware:
    """Tests for the CSRF middleware."""

    def test_mutation_without_header_returns_403(self):
        app = _make_test_app()
        client = TestClient(app)
        response = client.post(
            "/graphql",
            json={"query": "mutation { createUser(input: {}) { id } }"},
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["errors"][0]["message"]

    def test_mutation_with_header_succeeds(self):
        app = _make_test_app()
        client = TestClient(app)
        response = client.post(
            "/graphql",
            json={"query": "mutation { createUser(input: {}) { id } }"},
            headers={"X-Requested-With": "NinjaStack"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["ok"] is True

    def test_query_without_header_succeeds(self):
        """Non-mutation queries should not require CSRF token."""
        app = _make_test_app()
        client = TestClient(app)
        response = client.post(
            "/graphql",
            json={"query": "query { getUser(id: 1) { name } }"},
        )
        assert response.status_code == 200

    def test_csrf_disabled_allows_all(self):
        app = _make_test_app(CSRFConfig(enabled=False))
        client = TestClient(app)
        response = client.post(
            "/graphql",
            json={"query": "mutation { deleteUser(id: 1) }"},
        )
        assert response.status_code == 200

    def test_samesite_cookie_set(self):
        app = _make_test_app()
        client = TestClient(app)
        response = client.post(
            "/graphql",
            json={"query": "query { getUser(id: 1) { name } }"},
        )
        cookies = response.headers.get("set-cookie", "")
        assert "ninjastack_csrf" in cookies

    def test_custom_header_name(self):
        config = CSRFConfig(header_name="X-CSRF-Token")
        app = _make_test_app(config)
        client = TestClient(app)

        # Without the custom header
        response = client.post(
            "/graphql",
            json={"query": "mutation { createUser { id } }"},
            headers={"X-Requested-With": "anything"},
        )
        assert response.status_code == 403

        # With the custom header
        response = client.post(
            "/graphql",
            json={"query": "mutation { createUser { id } }"},
            headers={"X-CSRF-Token": "valid-token"},
        )
        assert response.status_code == 200
