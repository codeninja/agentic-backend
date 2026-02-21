"""Tests for the FastAPI app factory, health endpoint, and CORS."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from ninja_api.app import _parse_cors_origins, create_app


@pytest.fixture()
def app(asd_file: Path, connections_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a test app with mocked startup dependencies."""
    # Change to the tmp dir so relative path lookups for connections/auth work.
    monkeypatch.chdir(asd_file.parent.parent)
    return create_app(schema_path=asd_file)


@pytest.fixture()
async def client(app) -> httpx.AsyncClient:
    """Return an async HTTP client wired to the test app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_health_no_auth_required(self, client: httpx.AsyncClient) -> None:
        """Health endpoint should be accessible without any auth headers."""
        resp = await client.get("/health")
        assert resp.status_code == 200


class TestCorsHeaders:
    async def test_cors_headers_present(self, client: httpx.AsyncClient) -> None:
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in resp.headers

    def test_parse_cors_origins_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NINJA_CORS_ORIGINS", raising=False)
        assert _parse_cors_origins() == ["*"]

    def test_parse_cors_origins_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NINJA_CORS_ORIGINS", "http://localhost:3000,https://app.example.com")
        origins = _parse_cors_origins()
        assert origins == ["http://localhost:3000", "https://app.example.com"]

    def test_parse_cors_origins_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NINJA_CORS_ORIGINS", " http://a.com , http://b.com ")
        origins = _parse_cors_origins()
        assert origins == ["http://a.com", "http://b.com"]


class TestAppFactory:
    def test_create_app_returns_fastapi(self, asd_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi import FastAPI

        monkeypatch.chdir(asd_file.parent.parent)
        app = create_app(schema_path=asd_file)
        assert isinstance(app, FastAPI)

    async def test_graphql_playground_accessible(self, client: httpx.AsyncClient) -> None:
        """The /graphql endpoint should serve the Strawberry GraphQL playground."""
        resp = await client.get("/graphql")
        # Strawberry returns HTML for GET requests (playground).
        assert resp.status_code == 200


class TestGraphQLExecution:
    async def test_graphql_query_executes(self, client: httpx.AsyncClient) -> None:
        """A simple introspection query should succeed."""
        resp = await client.post(
            "/graphql",
            json={"query": "{ __schema { queryType { name } } }"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["__schema"]["queryType"]["name"] == "Query"
