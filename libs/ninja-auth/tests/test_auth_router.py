"""Tests for the OAuth2 auth router factory."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from ninja_auth.config import AuthConfig, OAuth2ProviderConfig
from ninja_auth.context import UserContext
from ninja_auth.router import create_auth_router
from ninja_auth.state_store import InMemoryOAuthStateStore
from ninja_auth.strategies.identity import IdentityStrategy


def _make_config() -> AuthConfig:
    """Create a test AuthConfig with a Google OAuth2 provider."""
    return AuthConfig(
        oauth2_providers={
            "google": OAuth2ProviderConfig(
                client_id="test-client-id",
                client_secret="test-client-secret",
                authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
                userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
                redirect_uri="https://myapp.com/auth/google/callback",
                scopes=["openid", "email", "profile"],
            ),
        },
    )


def _build_app(config: AuthConfig | None = None, **router_kwargs) -> FastAPI:
    """Build a FastAPI app with the auth router mounted."""
    cfg = config or _make_config()
    app = FastAPI()
    router = create_auth_router(cfg, **router_kwargs)
    app.include_router(router)
    return app


@pytest.fixture
def config() -> AuthConfig:
    return _make_config()


@pytest.fixture
def state_store() -> InMemoryOAuthStateStore:
    return InMemoryOAuthStateStore()


@pytest.fixture
def app(config: AuthConfig, state_store: InMemoryOAuthStateStore) -> FastAPI:
    return _build_app(config, state_store=state_store)


async def test_authorize_redirects_to_provider(app: FastAPI):
    """GET /auth/{provider}/authorize should redirect to the OAuth2 provider."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        resp = await client.get("/auth/google/authorize")

    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "accounts.google.com" in location
    assert "client_id=test-client-id" in location
    assert "state=" in location
    assert "response_type=code" in location


async def test_authorize_stores_state(config: AuthConfig, state_store: InMemoryOAuthStateStore):
    """The authorize endpoint should persist a state token in the state store."""
    app = _build_app(config, state_store=state_store)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        resp = await client.get("/auth/google/authorize")

    # Extract state from redirect URL
    location = resp.headers["location"]
    # Parse state param from URL
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(location).query)
    state_token = query["state"][0]

    # Verify state was stored
    metadata = await state_store.get_state(state_token)
    assert metadata is not None
    assert metadata["provider"] == "google"


async def test_authorize_unknown_provider_returns_404(app: FastAPI):
    """Requesting an unknown provider should return 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/unknown/authorize")

    assert resp.status_code == 404
    assert "Unknown OAuth2 provider" in resp.json()["detail"]


async def test_callback_success(config: AuthConfig, state_store: InMemoryOAuthStateStore):
    """A valid callback should exchange the code and return a JWT."""
    app = _build_app(config, state_store=state_store)

    # Pre-store a state token
    state_token = "valid-state-token"
    await state_store.save_state(state_token, {"provider": "google"})

    mock_user_ctx = UserContext(
        user_id="user-123",
        email="user@example.com",
        roles=[],
        provider="oauth2:google",
    )

    with patch(
        "ninja_auth.router.OAuth2Strategy.authenticate_with_code",
        new_callable=AsyncMock,
        return_value=mock_user_ctx,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/auth/google/callback",
                params={"code": "auth-code-123", "state": state_token},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user_id"] == "user-123"
    assert body["email"] == "user@example.com"


async def test_callback_deletes_state_after_use(config: AuthConfig, state_store: InMemoryOAuthStateStore):
    """State token should be deleted after successful callback to prevent replay."""
    app = _build_app(config, state_store=state_store)

    state_token = "one-time-state"
    await state_store.save_state(state_token, {"provider": "google"})

    mock_user_ctx = UserContext(
        user_id="user-123",
        email="user@example.com",
        roles=[],
        provider="oauth2:google",
    )

    with patch(
        "ninja_auth.router.OAuth2Strategy.authenticate_with_code",
        new_callable=AsyncMock,
        return_value=mock_user_ctx,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/auth/google/callback",
                params={"code": "code-abc", "state": state_token},
            )

    assert resp.status_code == 200

    # State should have been deleted
    result = await state_store.get_state(state_token)
    assert result is None


async def test_callback_invalid_state_returns_403(config: AuthConfig, state_store: InMemoryOAuthStateStore):
    """Callback with an unknown state token should return 403."""
    app = _build_app(config, state_store=state_store)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": "bogus-state"},
        )

    assert resp.status_code == 403
    assert "Invalid or expired" in resp.json()["detail"]


async def test_callback_unknown_provider_returns_404(app: FastAPI):
    """Callback to an unknown provider should return 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/auth/unknown/callback",
            params={"code": "code", "state": "state"},
        )

    assert resp.status_code == 404


async def test_callback_code_exchange_failure_returns_502(config: AuthConfig, state_store: InMemoryOAuthStateStore):
    """If authenticate_with_code raises AuthenticationError, return 502."""
    from ninja_auth.errors import AuthenticationError

    app = _build_app(config, state_store=state_store)

    state_token = "valid-state"
    await state_store.save_state(state_token, {"provider": "google"})

    with patch(
        "ninja_auth.router.OAuth2Strategy.authenticate_with_code",
        new_callable=AsyncMock,
        side_effect=AuthenticationError("Token exchange failed"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/auth/google/callback",
                params={"code": "bad-code", "state": state_token},
            )

    assert resp.status_code == 502
    assert "Token exchange failed" in resp.json()["detail"]


async def test_callback_unexpected_error_returns_502(config: AuthConfig, state_store: InMemoryOAuthStateStore):
    """If authenticate_with_code raises an unexpected error, return 502."""
    app = _build_app(config, state_store=state_store)

    state_token = "valid-state-2"
    await state_store.save_state(state_token, {"provider": "google"})

    with patch(
        "ninja_auth.router.OAuth2Strategy.authenticate_with_code",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Network timeout"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/auth/google/callback",
                params={"code": "code", "state": state_token},
            )

    assert resp.status_code == 502
    assert "Failed to complete OAuth2 code exchange" in resp.json()["detail"]


async def test_callback_jwt_is_valid(config: AuthConfig, state_store: InMemoryOAuthStateStore):
    """The JWT returned by callback should be decodable by IdentityStrategy."""
    app = _build_app(config, state_store=state_store)

    state_token = "jwt-test-state"
    await state_store.save_state(state_token, {"provider": "google"})

    mock_user_ctx = UserContext(
        user_id="uid-456",
        email="jwt@example.com",
        roles=["user"],
        provider="oauth2:google",
    )

    with patch(
        "ninja_auth.router.OAuth2Strategy.authenticate_with_code",
        new_callable=AsyncMock,
        return_value=mock_user_ctx,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/auth/google/callback",
                params={"code": "code-xyz", "state": state_token},
            )

    body = resp.json()
    token = body["access_token"]

    # Validate the JWT using an IdentityStrategy with the same config
    identity = IdentityStrategy(config.identity)
    validated = identity.validate_token(token)
    assert validated is not None
    assert validated.user_id == "uid-456"
    assert validated.email == "jwt@example.com"


async def test_router_with_custom_prefix(config: AuthConfig):
    """The router should respect a custom prefix."""
    app = FastAPI()
    router = create_auth_router(config, prefix="/oauth")
    app.include_router(router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        resp = await client.get("/oauth/google/authorize")

    assert resp.status_code == 302


async def test_callback_missing_code_returns_422(app: FastAPI):
    """Missing required query param 'code' should return 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/google/callback", params={"state": "s"})

    assert resp.status_code == 422


async def test_callback_missing_state_returns_422(app: FastAPI):
    """Missing required query param 'state' should return 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/google/callback", params={"code": "c"})

    assert resp.status_code == 422
