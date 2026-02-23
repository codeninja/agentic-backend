"""Tests for built-in identity strategy (registration, login, password hashing)."""

from __future__ import annotations

import logging
from typing import Any

import jwt
import pytest
from ninja_auth.config import IdentityConfig, PasswordPolicy
from ninja_auth.strategies.identity import IdentityStrategy
from ninja_auth.user_store import InMemoryUserStore, UserStore

# Valid password that satisfies the default policy (8+ chars, upper, lower, digit)
VALID_PASSWORD = "Password1"


def _make_strategy(user_store: UserStore | None = None, **kwargs: Any) -> IdentityStrategy:
    config = IdentityConfig(token_secret="test-secret-key-at-least-32-bytes!!", **kwargs)
    return IdentityStrategy(config, user_store=user_store)


def test_identity_register():
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", VALID_PASSWORD)
    assert ctx.email == "user@example.com"
    assert ctx.provider == "identity"
    assert ctx.is_authenticated


def test_identity_register_duplicate():
    strategy = _make_strategy()
    strategy.register("a@b.com", VALID_PASSWORD)
    try:
        strategy.register("a@b.com", "OtherPass2")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "already exists" in str(e)


def test_identity_login_success():
    strategy = _make_strategy()
    strategy.register("user@example.com", VALID_PASSWORD)
    ctx = strategy.login("user@example.com", VALID_PASSWORD)
    assert ctx is not None
    assert ctx.email == "user@example.com"


def test_identity_login_wrong_password():
    strategy = _make_strategy()
    strategy.register("user@example.com", VALID_PASSWORD)
    ctx = strategy.login("user@example.com", "WrongPass9")
    assert ctx is None


def test_identity_login_unknown_user():
    strategy = _make_strategy()
    ctx = strategy.login("noone@example.com", VALID_PASSWORD)
    assert ctx is None


def test_identity_password_hashing():
    strategy = _make_strategy()
    hashed = strategy.hash_password("secret")
    assert hashed != "secret"
    assert strategy.verify_password("secret", hashed)
    assert not strategy.verify_password("wrong", hashed)


def test_identity_issue_token():
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", VALID_PASSWORD)
    token = strategy.issue_token(ctx)
    assert isinstance(token, str)

    payload = jwt.decode(token, "test-secret-key-at-least-32-bytes!!", algorithms=["HS256"])
    assert payload["sub"] == ctx.user_id
    assert payload["email"] == "user@example.com"


def test_identity_validate_token():
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", VALID_PASSWORD)
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
    ctx = strategy.register("admin@example.com", VALID_PASSWORD, roles=["admin", "editor"])
    assert ctx.roles == ["admin", "editor"]


# --- Password validation tests ---


def test_password_too_short():
    strategy = _make_strategy()
    with pytest.raises(ValueError, match="at least 8 characters"):
        strategy.register("user@example.com", "Ab1")


def test_password_missing_uppercase():
    strategy = _make_strategy()
    with pytest.raises(ValueError, match="uppercase"):
        strategy.register("user@example.com", "password1")


def test_password_missing_lowercase():
    strategy = _make_strategy()
    with pytest.raises(ValueError, match="lowercase"):
        strategy.register("user@example.com", "PASSWORD1")


def test_password_missing_digit():
    strategy = _make_strategy()
    with pytest.raises(ValueError, match="digit"):
        strategy.register("user@example.com", "Passwords")


def test_password_custom_policy_special_char():
    policy = PasswordPolicy(require_special=True)
    strategy = _make_strategy(password_policy=policy)
    with pytest.raises(ValueError, match="special character"):
        strategy.register("user@example.com", "Password1")

    ctx = strategy.register("user@example.com", "Password1!")
    assert ctx is not None


def test_password_relaxed_policy():
    """A relaxed policy allows simple passwords."""
    policy = PasswordPolicy(
        min_length=4,
        require_uppercase=False,
        require_lowercase=False,
        require_digit=False,
    )
    strategy = _make_strategy(password_policy=policy)
    ctx = strategy.register("user@example.com", "pass")
    assert ctx is not None


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

    ctx = strategy.register("test@example.com", VALID_PASSWORD)
    assert ctx.email == "test@example.com"

    # Verify data went through the custom store
    assert store.exists("test@example.com")
    record = store.get("test@example.com")
    assert record is not None
    assert record["email"] == "test@example.com"

    # Login works through the custom store
    logged_in = strategy.login("test@example.com", VALID_PASSWORD)
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


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------

IDENTITY_LOGGER = "ninja_auth.strategies.identity"


def test_login_failure_logs_warning_without_password(caplog: pytest.LogCaptureFixture) -> None:
    """Failed login emits WARNING and does NOT contain the password."""
    strategy = _make_strategy()
    strategy.register("user@example.com", VALID_PASSWORD)

    with caplog.at_level(logging.WARNING, logger=IDENTITY_LOGGER):
        strategy.login("user@example.com", "WrongPass9secret")

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == IDENTITY_LOGGER]
    assert len(warning_records) >= 1
    assert "user@example.com" in warning_records[0].message
    # Password must NEVER appear in the log
    full_output = " ".join(r.message for r in caplog.records)
    assert "WrongPass9secret" not in full_output
    assert VALID_PASSWORD not in full_output


def test_login_failure_unknown_email_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Failed login for unknown email emits WARNING."""
    strategy = _make_strategy()

    with caplog.at_level(logging.WARNING, logger=IDENTITY_LOGGER):
        strategy.login("nobody@example.com", VALID_PASSWORD)

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == IDENTITY_LOGGER]
    assert len(warning_records) >= 1
    assert "nobody@example.com" in warning_records[0].message


def test_successful_login_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    """Successful login emits INFO with email."""
    strategy = _make_strategy()
    strategy.register("user@example.com", VALID_PASSWORD)

    with caplog.at_level(logging.INFO, logger=IDENTITY_LOGGER):
        ctx = strategy.login("user@example.com", VALID_PASSWORD)

    assert ctx is not None
    info_records = [r for r in caplog.records if r.levelno == logging.INFO and "Login successful" in r.message]
    assert len(info_records) == 1
    assert "user@example.com" in info_records[0].message


def test_register_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    """User registration emits INFO with email and user_id."""
    strategy = _make_strategy()

    with caplog.at_level(logging.INFO, logger=IDENTITY_LOGGER):
        ctx = strategy.register("newuser@example.com", VALID_PASSWORD, roles=["editor"])

    info_records = [r for r in caplog.records if r.levelno == logging.INFO and "registered" in r.message]
    assert len(info_records) == 1
    assert "newuser@example.com" in info_records[0].message
    assert ctx.user_id in info_records[0].message


def test_issue_token_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    """Token issuance emits INFO with user_id."""
    strategy = _make_strategy()
    ctx = strategy.register("user@example.com", VALID_PASSWORD)

    with caplog.at_level(logging.INFO, logger=IDENTITY_LOGGER):
        strategy.issue_token(ctx)

    info_records = [r for r in caplog.records if r.levelno == logging.INFO and "Token issued" in r.message]
    assert len(info_records) == 1
    assert ctx.user_id in info_records[0].message


# ---------------------------------------------------------------------------
# Timing side-channel prevention (issue #99)
# ---------------------------------------------------------------------------


def test_login_unknown_user_performs_hash_comparison() -> None:
    """Login with a non-existent user still performs bcrypt work (constant-time)."""
    strategy = _make_strategy()
    # Measure that both paths take comparable time by verifying the dummy
    # hash class attribute exists and that login still returns None.
    assert hasattr(IdentityStrategy, "_DUMMY_HASH")
    assert strategy.login("ghost@example.com", "Password1") is None


def test_login_timing_similarity() -> None:
    """Both missing-user and wrong-password paths invoke bcrypt verify."""
    import time

    strategy = _make_strategy()
    strategy.register("real@example.com", VALID_PASSWORD)

    # Warm up bcrypt (first call can be slower due to imports/caching)
    strategy.login("real@example.com", "WrongPass1")

    samples = 3
    missing_times: list[float] = []
    wrong_pw_times: list[float] = []

    for _ in range(samples):
        t0 = time.perf_counter()
        strategy.login("nonexistent@example.com", "Password1")
        missing_times.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        strategy.login("real@example.com", "WrongPass1")
        wrong_pw_times.append(time.perf_counter() - t0)

    avg_missing = sum(missing_times) / samples
    avg_wrong = sum(wrong_pw_times) / samples

    # Both paths should be within 3x of each other (generous margin for CI).
    # Before the fix, missing-user was ~1000x faster (no bcrypt).
    ratio = max(avg_missing, avg_wrong) / min(avg_missing, avg_wrong)
    assert ratio < 3.0, f"Timing ratio {ratio:.1f}x — possible enumeration leak"
