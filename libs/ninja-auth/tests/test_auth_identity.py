"""Tests for built-in identity strategy (registration, login, password hashing)."""

from __future__ import annotations

from typing import Any

import jwt
from ninja_auth.config import IdentityConfig
from ninja_auth.strategies.identity import IdentityStrategy
from ninja_auth.user_store import InMemoryUserStore, UserStore


def _make_strategy(user_store: UserStore | None = None, **kwargs: Any) -> IdentityStrategy:
    config = IdentityConfig(token_secret="test-secret-key-at-least-32-bytes!!", **kwargs)
    return IdentityStrategy(config, user_store=user_store)


def test_identity_register():
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", "password123")
    assert ctx.email == "user@example.com"
    assert ctx.provider == "identity"
    assert ctx.is_authenticated


def test_identity_register_duplicate():
    strategy = _make_strategy()
    strategy.register("a@b.com", "pass")
    try:
        strategy.register("a@b.com", "pass2")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "already exists" in str(e)


def test_identity_login_success():
    strategy = _make_strategy()
    strategy.register("user@example.com", "mypassword")
    ctx = strategy.login("user@example.com", "mypassword")
    assert ctx is not None
    assert ctx.email == "user@example.com"


def test_identity_login_wrong_password():
    strategy = _make_strategy()
    strategy.register("user@example.com", "correct")
    ctx = strategy.login("user@example.com", "wrong")
    assert ctx is None


def test_identity_login_unknown_user():
    strategy = _make_strategy()
    ctx = strategy.login("noone@example.com", "pass")
    assert ctx is None


def test_identity_password_hashing():
    strategy = _make_strategy()
    hashed = strategy.hash_password("secret")
    assert hashed != "secret"
    assert strategy.verify_password("secret", hashed)
    assert not strategy.verify_password("wrong", hashed)


def test_identity_issue_token():
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", "pass")
    token = strategy.issue_token(ctx)
    assert isinstance(token, str)

    payload = jwt.decode(token, "test-secret-key-at-least-32-bytes!!", algorithms=["HS256"])
    assert payload["sub"] == ctx.user_id
    assert payload["email"] == "user@example.com"


def test_identity_validate_token():
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", "pass")
    token = strategy.issue_token(ctx)
    validated = strategy.validate_token(token)
    assert validated is not None
    assert validated.user_id == ctx.user_id
    assert validated.email == "user@example.com"
    assert validated.provider == "identity"


def test_identity_validate_invalid_token():
    strategy = _make_strategy()
    ctx = strategy.validate_token("invalid.token.here")
    assert ctx is None


def test_identity_register_with_roles():
    strategy = _make_strategy()
    ctx = strategy.register("admin@example.com", "pass", roles=["admin", "editor"])
    assert ctx.roles == ["admin", "editor"]


# --- UserStore protocol tests ---


def test_default_uses_in_memory_store():
    """IdentityStrategy defaults to InMemoryUserStore when no store is provided."""
    strategy = _make_strategy()
    assert isinstance(strategy._store, InMemoryUserStore)


def test_custom_user_store_injection():
    """A custom UserStore implementation can be injected."""

    class FakeUserStore:
        def __init__(self) -> None:
            self._data: dict[str, dict[str, Any]] = {}

        def get(self, email: str) -> dict[str, Any] | None:
            return self._data.get(email)

        def save(self, email: str, data: dict[str, Any]) -> None:
            self._data[email] = data

        def exists(self, email: str) -> bool:
            return email in self._data

    store = FakeUserStore()
    strategy = _make_strategy(user_store=store)

    ctx = strategy.register("test@example.com", "pass123")
    assert ctx.email == "test@example.com"

    # Verify data went through the custom store
    assert store.exists("test@example.com")
    record = store.get("test@example.com")
    assert record is not None
    assert record["email"] == "test@example.com"

    # Login works through the custom store
    logged_in = strategy.login("test@example.com", "pass123")
    assert logged_in is not None
    assert logged_in.email == "test@example.com"


def test_user_store_protocol_compliance():
    """InMemoryUserStore satisfies the UserStore protocol."""
    assert isinstance(InMemoryUserStore(), UserStore)


def test_in_memory_store_warns(caplog: Any) -> None:
    """InMemoryUserStore emits a warning at init."""
    import logging

    with caplog.at_level(logging.WARNING, logger="ninja_auth.user_store"):
        InMemoryUserStore()

    assert any("in-memory user store" in r.message for r in caplog.records)
