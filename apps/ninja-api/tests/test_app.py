"""Tests for the ninja-api FastAPI composition shell."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import strawberry
from ninja_core import AgenticSchema
from ninja_core.schema.entity import EntitySchema, FieldSchema, StorageEngine
from starlette.testclient import TestClient

# AuthConfig's BearerConfig requires a secret_key unless NINJASTACK_ENV=test
os.environ.setdefault("NINJASTACK_ENV", "test")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_asd() -> AgenticSchema:
    """Return a minimal ASD with one entity for testing."""
    return AgenticSchema(
        project_name="test",
        entities=[
            EntitySchema(
                name="User",
                storage_engine=StorageEngine.SQL,
                fields=[
                    FieldSchema(name="id", field_type="string", primary_key=True),
                    FieldSchema(name="email", field_type="string"),
                ],
            ),
        ],
    )


@strawberry.type
class _StubQuery:
    @strawberry.field
    def hello(self) -> str:
        return "world"


def _stub_schema() -> strawberry.Schema:
    return strawberry.Schema(query=_StubQuery)


@contextmanager
def _patched_client(
    asd: AgenticSchema | None = None,
    conn_mgr: Any = None,
    schema: Any = None,
    load_raises: Exception | None = None,
    empty_profiles: bool = False,
):
    """Yield a TestClient with all library dependencies patched.

    Patches remain active for the entire lifespan (startup + requests + shutdown).
    """
    _asd = asd if asd is not None else _minimal_asd()
    _schema = schema or _stub_schema()
    _conn_mgr = conn_mgr

    if _conn_mgr is None:
        _conn_mgr = MagicMock()
        _conn_mgr.close_all = AsyncMock()
        if empty_profiles:
            _conn_mgr.profiles = {}
        else:
            _conn_mgr.profiles = {"default": MagicMock()}

    load_schema_mock = MagicMock(return_value=_asd)
    if load_raises:
        load_schema_mock.side_effect = load_raises

    from_file_mock = MagicMock(return_value=_conn_mgr)

    # Make all paths public in test so we can exercise route logic without auth
    from ninja_auth import AuthConfig

    test_auth_config = AuthConfig.from_file()
    test_auth_config.public_paths = ["/*"]

    # Force fresh import so module picks up the latest code
    sys.modules.pop("ninja_api", None)
    import ninja_api

    with (
        patch.object(ninja_api, "load_schema", load_schema_mock),
        patch.object(ninja_api.ConnectionManager, "from_file", from_file_mock),
        patch.object(ninja_api, "build_schema", return_value=_schema),
        patch.object(ninja_api, "AdapterRegistry", return_value=MagicMock()),
        patch.object(ninja_api.AuthConfig, "from_file", return_value=test_auth_config),
    ):
        app = ninja_api.create_app()
        with TestClient(app) as client:
            yield client, app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_ok(self) -> None:
        with _patched_client() as (client, _app):
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["schema_loaded"] is True

    def test_health_when_schema_missing(self) -> None:
        """When schema.json is missing, app starts with fallback empty schema."""
        with _patched_client(load_raises=FileNotFoundError("not found")) as (client, _app):
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            # Even with the fallback empty schema, asd is set
            assert body["schema_loaded"] is True


class TestGraphQLMount:
    """Tests for the /graphql endpoint."""

    def test_graphql_post_query(self) -> None:
        with _patched_client() as (client, _app):
            resp = client.post(
                "/graphql",
                json={"query": "{ hello }"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["data"]["hello"] == "world"


class TestCORS:
    """Tests for CORS middleware configuration."""

    def test_cors_allows_all_by_default(self) -> None:
        with _patched_client() as (client, _app):
            resp = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert resp.headers.get("access-control-allow-origin") == "*"

    def test_cors_uses_env_var(self) -> None:
        with patch.dict("os.environ", {"CORS_ORIGINS": "http://example.com,http://foo.com"}):
            with _patched_client() as (client, _app):
                resp = client.options(
                    "/health",
                    headers={
                        "Origin": "http://example.com",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                assert "http://example.com" in resp.headers.get("access-control-allow-origin", "")


class TestChatEndpoint:
    """Tests for POST /chat."""

    def test_chat_without_orchestrator_returns_error(self) -> None:
        with _patched_client() as (client, _app):
            resp = client.post("/chat", json={"message": "hello"})
            assert resp.status_code == 200
            assert resp.json()["error"] == "Agent orchestrator not initialized"

    def test_chat_with_orchestrator(self) -> None:
        with _patched_client() as (client, app):
            orchestrator = MagicMock()
            orchestrator.fan_out = AsyncMock(return_value={"sales": {"answer": "42"}})
            app.state.orchestrator = orchestrator
            resp = client.post(
                "/chat",
                json={"message": "What are sales?", "target_domains": ["sales"]},
            )
            assert resp.status_code == 200
            assert resp.json() == {"sales": {"answer": "42"}}
            orchestrator.fan_out.assert_called_once_with("What are sales?", target_domains=["sales"])


class TestGracefulDegradation:
    """Tests for graceful handling of missing config files."""

    def test_empty_connection_profiles(self) -> None:
        """App starts without persistence when no connection profiles exist."""
        with _patched_client(empty_profiles=True) as (client, _app):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_shutdown_closes_connections(self) -> None:
        """Lifespan shutdown calls close_all on connection manager."""
        conn_mgr = MagicMock()
        conn_mgr.close_all = AsyncMock()
        with _patched_client(conn_mgr=conn_mgr) as (_client, _app):
            pass  # triggers lifespan enter and exit
        conn_mgr.close_all.assert_called_once()


class TestRepoGetter:
    """Tests for the _make_repo_getter adapter."""

    def test_repo_getter_returns_repository(self) -> None:
        sys.modules.pop("ninja_api", None)
        import ninja_api

        asd = _minimal_asd()
        registry = MagicMock()
        registry.get_repository.return_value = MagicMock()

        getter = ninja_api._make_repo_getter(asd, registry)
        repo = getter("User")

        assert repo is not None
        registry.get_repository.assert_called_once()
        # Verify it was called with the EntitySchema, not a string
        call_args = registry.get_repository.call_args[0]
        assert call_args[0].name == "User"

    def test_repo_getter_unknown_entity_raises(self) -> None:
        sys.modules.pop("ninja_api", None)
        import ninja_api

        asd = _minimal_asd()
        registry = MagicMock()

        getter = ninja_api._make_repo_getter(asd, registry)

        with pytest.raises(ValueError, match="Unknown entity: Nonexistent"):
            getter("Nonexistent")
