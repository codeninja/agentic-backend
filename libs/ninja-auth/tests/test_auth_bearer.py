"""Tests for Bearer (JWT) strategy."""

import logging
from datetime import datetime, timezone

import jwt
import pytest
from ninja_auth.config import BearerConfig
from ninja_auth.strategies.bearer import BearerStrategy
from starlette.testclient import TestClient

SECRET = "test-secret-key-that-is-at-least-32-bytes-long"


def _make_token(payload: dict, secret: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_bearer_valid_token():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1", "email": "a@b.com", "roles": ["admin"]})
    ctx = strategy.validate_token(token)
    assert ctx is not None
    assert ctx.user_id == "user1"
    assert ctx.email == "a@b.com"
    assert "admin" in ctx.roles
    assert ctx.provider == "bearer"


def test_bearer_expired_token():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token(
        {
            "sub": "user1",
            "exp": datetime(2020, 1, 1, tzinfo=timezone.utc),
        }
    )
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_invalid_signature():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1"}, secret="wrong-secret-key-that-is-32-bytes-long!")
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_invalid_token_string():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    ctx = strategy.validate_token("not.a.valid.jwt")
    assert ctx is None


def test_bearer_with_issuer_validation():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256", issuer="https://auth.example.com")
    strategy = BearerStrategy(config)

    # Valid issuer
    token = _make_token({"sub": "u1", "iss": "https://auth.example.com"})
    ctx = strategy.validate_token(token)
    assert ctx is not None

    # Wrong issuer
    token = _make_token({"sub": "u1", "iss": "https://evil.com"})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_with_audience_validation():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256", audience="my-app")
    strategy = BearerStrategy(config)

    token = _make_token({"sub": "u1", "aud": "my-app"})
    ctx = strategy.validate_token(token)
    assert ctx is not None

    token = _make_token({"sub": "u1", "aud": "other-app"})
    ctx = strategy.validate_token(token)
    assert ctx is None


async def test_bearer_authenticate_from_header():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)

    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def homepage(request):
        ctx = await strategy.authenticate(request)
        if ctx:
            return JSONResponse({"user_id": ctx.user_id})
        return JSONResponse({"user_id": None})

    app = Starlette(routes=[Route("/", homepage)])
    client = TestClient(app)

    token = _make_token({"sub": "user1"})
    resp = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["user_id"] == "user1"

    # No header
    resp = client.get("/")
    assert resp.json()["user_id"] is None


def test_bearer_rejects_token_missing_sub():
    """JWT without a 'sub' claim must be rejected (issue #81)."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"email": "a@b.com", "roles": ["admin"]})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_rejects_token_with_empty_sub():
    """JWT with an empty-string 'sub' claim must be rejected (issue #81)."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "", "email": "a@b.com"})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_rejects_token_with_whitespace_sub():
    """JWT with a whitespace-only 'sub' claim must be rejected."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "   ", "email": "a@b.com"})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_metadata_contains_claims():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1", "custom_field": "value"})
    ctx = strategy.validate_token(token)
    assert ctx is not None
    assert "claims" in ctx.metadata
    assert ctx.metadata["claims"]["custom_field"] == "value"


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------

BEARER_LOGGER = "ninja_auth.strategies.bearer"


def test_bearer_expired_token_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Expired token emits WARNING with reason."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1", "exp": datetime(2020, 1, 1, tzinfo=timezone.utc)})

    with caplog.at_level(logging.WARNING, logger=BEARER_LOGGER):
        ctx = strategy.validate_token(token)

    assert ctx is None
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) >= 1
    assert "expired" in warning_records[0].message.lower()


def test_bearer_invalid_signature_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    """Invalid signature emits ERROR with reason."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1"}, secret="wrong-secret-key-that-is-32-bytes-long!")

    with caplog.at_level(logging.ERROR, logger=BEARER_LOGGER):
        ctx = strategy.validate_token(token)

    assert ctx is None
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) >= 1


def test_bearer_malformed_token_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    """Malformed token emits ERROR."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)

    with caplog.at_level(logging.ERROR, logger=BEARER_LOGGER):
        ctx = strategy.validate_token("not.a.valid.jwt")

    assert ctx is None
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) >= 1
