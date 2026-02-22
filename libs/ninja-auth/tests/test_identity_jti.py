"""Tests verifying that IdentityStrategy.issue_token() includes a unique jti claim."""

from __future__ import annotations

import jwt
from ninja_auth.config import IdentityConfig
from ninja_auth.strategies.identity import IdentityStrategy

SECRET = "test-secret-key-at-least-32-bytes!!"


def _make_strategy() -> IdentityStrategy:
    config = IdentityConfig(token_secret=SECRET)
    return IdentityStrategy(config)


def test_issue_token_includes_jti():
    """Every issued token must contain a jti claim."""
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", "Password1")
    token = strategy.issue_token(ctx)

    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert "jti" in payload
    assert isinstance(payload["jti"], str)
    assert len(payload["jti"]) == 32  # uuid4().hex is 32 hex chars


def test_issue_token_jti_is_unique():
    """Each issued token must have a distinct jti."""
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", "Password1")

    token1 = strategy.issue_token(ctx)
    token2 = strategy.issue_token(ctx)

    payload1 = jwt.decode(token1, SECRET, algorithms=["HS256"])
    payload2 = jwt.decode(token2, SECRET, algorithms=["HS256"])
    assert payload1["jti"] != payload2["jti"]


def test_issue_token_still_includes_standard_claims():
    """Adding jti must not break existing claims (sub, email, roles, iat, exp)."""
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", "Password1", roles=["admin"])
    token = strategy.issue_token(ctx)

    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert payload["sub"] == ctx.user_id
    assert payload["email"] == "user@example.com"
    assert payload["roles"] == ["admin"]
    assert "iat" in payload
    assert "exp" in payload
    assert "jti" in payload


def test_validate_token_still_works_with_jti():
    """validate_token must continue to work with tokens containing jti."""
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", "Password1")
    token = strategy.issue_token(ctx)

    validated = strategy.validate_token(token)
    assert validated is not None
    assert validated.user_id == ctx.user_id
    assert validated.email == "user@example.com"
