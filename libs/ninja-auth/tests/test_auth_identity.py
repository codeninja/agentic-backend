"""Tests for built-in identity strategy (registration, login, password hashing)."""

import jwt
from ninja_auth.config import IdentityConfig
from ninja_auth.strategies.identity import IdentityStrategy


def _make_strategy(**kwargs) -> IdentityStrategy:
    config = IdentityConfig(token_secret="test-secret", **kwargs)
    return IdentityStrategy(config)


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

    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
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
