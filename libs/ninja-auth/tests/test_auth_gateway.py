"""Tests for the AuthGateway middleware and context injection."""

import jwt
from ninja_auth.config import ApiKeyConfig, AuthConfig, BearerConfig
from ninja_auth.context import UserContext
from ninja_auth.gateway import AuthGateway, get_user_context
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

SECRET = "gw-test-secret-key-at-least-32-bytes-long!"


def _build_app(config: AuthConfig | None = None) -> Starlette:
    """Build a test Starlette app with the AuthGateway middleware."""

    async def protected(request: Request) -> JSONResponse:
        ctx: UserContext = request.state.user_context
        return JSONResponse({"user_id": ctx.user_id, "provider": ctx.provider})

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/protected", protected), Route("/health", health)])
    app.add_middleware(AuthGateway, config=config)
    return app


def _make_token(payload: dict) -> str:
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_gateway_public_path_allowed():
    config = AuthConfig(public_paths=["/health"])
    app = _build_app(config)
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_gateway_unauthenticated_returns_401():
    config = AuthConfig(bearer=BearerConfig(secret_key=SECRET))
    app = _build_app(config)
    client = TestClient(app)

    resp = client.get("/protected")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


def test_gateway_bearer_auth():
    config = AuthConfig(bearer=BearerConfig(secret_key=SECRET))
    app = _build_app(config)
    client = TestClient(app)

    token = _make_token({"sub": "user-1"})
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "user-1"
    assert resp.json()["provider"] == "bearer"


def test_gateway_apikey_auth():
    config = AuthConfig(
        bearer=BearerConfig(secret_key=SECRET),
        api_key=ApiKeyConfig(keys={"svc": "valid-key"}),
    )
    app = _build_app(config)
    client = TestClient(app)

    resp = client.get("/protected", headers={"X-API-Key": "valid-key"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "apikey:svc"


def test_gateway_invalid_bearer_falls_through():
    config = AuthConfig(
        bearer=BearerConfig(secret_key=SECRET),
        api_key=ApiKeyConfig(keys={"svc": "backup-key"}),
    )
    app = _build_app(config)
    client = TestClient(app)

    # Invalid JWT, but valid API key — should fall through to API key
    resp = client.get(
        "/protected",
        headers={"Authorization": "Bearer invalid.token", "X-API-Key": "backup-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "apikey"


def test_gateway_public_path_wildcard():
    config = AuthConfig(public_paths=["/docs*"])
    app = _build_app(config)

    async def docs(request):
        return JSONResponse({"page": "docs"})

    app.routes.append(Route("/docs/openapi", docs))
    client = TestClient(app)

    resp = client.get("/docs/openapi")
    assert resp.status_code == 200


def test_gateway_context_injection_into_request_state():
    """Verify UserContext is accessible via request.state.user_context."""
    config = AuthConfig(bearer=BearerConfig(secret_key=SECRET))

    async def endpoint(request: Request) -> JSONResponse:
        ctx = request.state.user_context
        return JSONResponse(
            {
                "user_id": ctx.user_id,
                "email": ctx.email,
                "roles": ctx.roles,
            }
        )

    app = Starlette(routes=[Route("/me", endpoint)])
    app.add_middleware(AuthGateway, config=config)
    client = TestClient(app)

    token = _make_token({"sub": "u1", "email": "a@b.com", "roles": ["admin"]})
    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "u1"
    assert data["email"] == "a@b.com"
    assert data["roles"] == ["admin"]


def test_get_user_context_dependency():
    """Test the FastAPI dependency function."""
    config = AuthConfig(bearer=BearerConfig(secret_key=SECRET))

    async def endpoint(request: Request) -> JSONResponse:
        ctx = get_user_context(request)
        return JSONResponse({"user_id": ctx.user_id})

    app = Starlette(routes=[Route("/dep", endpoint)])
    app.add_middleware(AuthGateway, config=config)
    client = TestClient(app)

    token = _make_token({"sub": "dep-user"})
    resp = client.get("/dep", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["user_id"] == "dep-user"


def test_get_user_context_returns_anonymous_when_missing():
    """get_user_context returns ANONYMOUS when no context is set."""

    async def endpoint(request: Request) -> JSONResponse:
        ctx = get_user_context(request)
        return JSONResponse({"authenticated": ctx.is_authenticated})

    app = Starlette(routes=[Route("/anon", endpoint)])
    client = TestClient(app)

    resp = client.get("/anon")
    assert resp.json()["authenticated"] is False


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------

GATEWAY_LOGGER = "ninja_auth.gateway"


def test_gateway_successful_auth_logs_info(caplog) -> None:
    """Successful authentication emits INFO with user_id, provider, ip, path."""
    import logging

    config = AuthConfig(bearer=BearerConfig(secret_key=SECRET))
    app = _build_app(config)
    client = TestClient(app)
    token = _make_token({"sub": "user-1"})

    with caplog.at_level(logging.INFO, logger=GATEWAY_LOGGER):
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    info_records = [r for r in caplog.records if r.levelno == logging.INFO and "Authentication successful" in r.message]
    assert len(info_records) == 1
    record = info_records[0]
    assert "user-1" in record.message
    assert "bearer" in record.message
    assert "/protected" in record.message
