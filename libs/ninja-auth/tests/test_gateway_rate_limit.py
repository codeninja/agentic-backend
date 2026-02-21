"""Tests for rate limiting integration in the AuthGateway middleware."""

import jwt
from ninja_auth.config import AuthConfig, BearerConfig
from ninja_auth.context import UserContext
from ninja_auth.gateway import AuthGateway
from ninja_auth.rate_limiter import RateLimitConfig
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

SECRET = "rate-limit-test-secret-key-32-bytes!"


def _build_app(config: AuthConfig) -> Starlette:
    async def protected(request: Request) -> JSONResponse:
        ctx: UserContext = request.state.user_context
        return JSONResponse({"user_id": ctx.user_id})

    app = Starlette(routes=[Route("/protected", protected)])
    app.add_middleware(AuthGateway, config=config)
    return app


def _make_token(payload: dict) -> str:
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_returns_429_after_too_many_failed_attempts():
    config = AuthConfig(
        bearer=BearerConfig(secret_key=SECRET),
        rate_limit=RateLimitConfig(max_attempts=3, window_seconds=60),
    )
    app = _build_app(config)
    client = TestClient(app)

    # Exhaust the rate limit with bad requests
    for _ in range(3):
        resp = client.get("/protected")
        assert resp.status_code == 401

    # Next request should be rate limited
    resp = client.get("/protected")
    assert resp.status_code == 429
    assert "Too many" in resp.json()["detail"]


def test_successful_auth_still_counts_toward_window():
    config = AuthConfig(
        bearer=BearerConfig(secret_key=SECRET),
        rate_limit=RateLimitConfig(max_attempts=3, window_seconds=60),
    )
    app = _build_app(config)
    client = TestClient(app)

    token = _make_token({"sub": "user-1"})
    for _ in range(3):
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    # Even valid auth is rate limited after window is full
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 429


def test_rate_limit_does_not_affect_public_paths():
    config = AuthConfig(
        public_paths=["/health"],
        bearer=BearerConfig(secret_key=SECRET),
        rate_limit=RateLimitConfig(max_attempts=1, window_seconds=60),
    )

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/health", health), Route("/protected", health)])
    app.add_middleware(AuthGateway, config=config)
    client = TestClient(app)

    # Exhaust the limit
    client.get("/protected")

    # Public path should still work
    resp = client.get("/health")
    assert resp.status_code == 200


def test_disabled_rate_limit_allows_unlimited_attempts():
    config = AuthConfig(
        bearer=BearerConfig(secret_key=SECRET),
        rate_limit=RateLimitConfig(enabled=False, max_attempts=1),
    )
    app = _build_app(config)
    client = TestClient(app)

    for _ in range(10):
        resp = client.get("/protected")
        assert resp.status_code == 401  # Not 429


def test_failed_auth_is_logged(caplog):
    config = AuthConfig(
        bearer=BearerConfig(secret_key=SECRET),
        rate_limit=RateLimitConfig(max_attempts=100, window_seconds=60),
    )
    app = _build_app(config)
    client = TestClient(app)

    import logging

    with caplog.at_level(logging.WARNING, logger="ninja_auth.gateway"):
        client.get("/protected")

    assert any("Authentication failed" in r.message for r in caplog.records)


def test_rate_limited_request_is_logged(caplog):
    config = AuthConfig(
        bearer=BearerConfig(secret_key=SECRET),
        rate_limit=RateLimitConfig(max_attempts=1, window_seconds=60),
    )
    app = _build_app(config)
    client = TestClient(app)

    import logging

    client.get("/protected")  # first attempt (fails, recorded)

    with caplog.at_level(logging.WARNING, logger="ninja_auth.gateway"):
        client.get("/protected")  # should be rate limited

    assert any("Rate limited" in r.message for r in caplog.records)
