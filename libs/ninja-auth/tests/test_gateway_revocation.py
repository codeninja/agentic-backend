"""Integration tests for token revocation in the AuthGateway."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import jwt
from ninja_auth.config import AuthConfig, BearerConfig
from ninja_auth.gateway import AuthGateway
from ninja_auth.revocation import InMemoryRevocationStore
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

SECRET = "gw-revocation-test-secret-key-32b!"


def _run(coro):
    """Helper to run async coroutines in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_app(config: AuthConfig) -> Starlette:
    """Build a test Starlette app with the AuthGateway middleware."""

    async def protected(request: Request) -> JSONResponse:
        ctx = request.state.user_context
        return JSONResponse({"user_id": ctx.user_id, "provider": ctx.provider})

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/protected", protected), Route("/health", health)])
    app.add_middleware(AuthGateway, config=config)
    return app


def _make_token(
    sub: str = "user-1",
    jti: str | None = "test-jti-123",
    iat: datetime | None = None,
    exp_minutes: int = 60,
) -> str:
    """Create a JWT with configurable claims."""
    now = iat or datetime.now(timezone.utc)
    payload: dict = {
        "sub": sub,
        "iat": now,
        "exp": now + timedelta(minutes=exp_minutes),
    }
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, SECRET, algorithm="HS256")


class TestGatewayWithRevocationDisabled:
    """When no revocation store is configured, gateway works as before."""

    def test_normal_auth_works_without_revocation_store(self) -> None:
        config = AuthConfig(bearer=BearerConfig(secret_key=SECRET))
        app = _build_app(config)
        client = TestClient(app)

        token = _make_token()
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user-1"

    def test_token_without_jti_works_when_no_revocation_store(self) -> None:
        config = AuthConfig(bearer=BearerConfig(secret_key=SECRET))
        app = _build_app(config)
        client = TestClient(app)

        token = _make_token(jti=None)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_public_paths_still_work(self) -> None:
        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            public_paths=["/health"],
        )
        app = _build_app(config)
        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 200


class TestGatewayWithTokenRevocation:
    """Per-token revocation via jti."""

    def test_revoked_token_returns_401(self) -> None:
        store = InMemoryRevocationStore()
        _run(store.revoke_token("revoked-jti"))

        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            revocation_store=store,
        )
        app = _build_app(config)
        client = TestClient(app)

        token = _make_token(jti="revoked-jti")
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Token has been revoked"

    def test_non_revoked_token_succeeds(self) -> None:
        store = InMemoryRevocationStore()
        _run(store.revoke_token("other-jti"))

        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            revocation_store=store,
        )
        app = _build_app(config)
        client = TestClient(app)

        token = _make_token(jti="clean-jti")
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user-1"

    def test_token_without_jti_passes_when_revocation_enabled(self) -> None:
        """Tokens without jti should still work even when revocation is enabled."""
        store = InMemoryRevocationStore()
        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            revocation_store=store,
        )
        app = _build_app(config)
        client = TestClient(app)

        token = _make_token(jti=None)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestGatewayWithUserRevocation:
    """Per-user session invalidation via revoked_before timestamp."""

    def test_token_issued_before_revocation_returns_401(self) -> None:
        store = InMemoryRevocationStore()
        # Token was issued 30 minutes ago (still valid with 60min expiry)
        old_iat = datetime.now(timezone.utc) - timedelta(minutes=30)
        # Revoke all tokens before "now"
        _run(store.revoke_all_user_tokens("user-1", before=datetime.now(timezone.utc)))

        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            revocation_store=store,
        )
        app = _build_app(config)
        client = TestClient(app)

        token = _make_token(sub="user-1", iat=old_iat)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Session invalidated"

    def test_token_issued_after_revocation_succeeds(self) -> None:
        store = InMemoryRevocationStore()
        # Revoke all tokens before an hour ago
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        _run(store.revoke_all_user_tokens("user-1", before=cutoff))

        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            revocation_store=store,
        )
        app = _build_app(config)
        client = TestClient(app)

        # Token issued now (after cutoff)
        token = _make_token(sub="user-1")
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_user_revocation_does_not_affect_other_users(self) -> None:
        store = InMemoryRevocationStore()
        _run(store.revoke_all_user_tokens("user-1", before=datetime.now(timezone.utc)))

        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            revocation_store=store,
        )
        app = _build_app(config)
        client = TestClient(app)

        # Token for user-2 should not be affected (30min ago, still valid)
        old_iat = datetime.now(timezone.utc) - timedelta(minutes=30)
        token = _make_token(sub="user-2", iat=old_iat)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestCombinedRevocation:
    """Both per-token and per-user revocation active simultaneously."""

    def test_jti_revocation_takes_priority(self) -> None:
        store = InMemoryRevocationStore()
        _run(store.revoke_token("combo-jti"))

        config = AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            revocation_store=store,
        )
        app = _build_app(config)
        client = TestClient(app)

        # Token is fresh (no user revocation) but jti is revoked
        token = _make_token(jti="combo-jti")
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Token has been revoked"
