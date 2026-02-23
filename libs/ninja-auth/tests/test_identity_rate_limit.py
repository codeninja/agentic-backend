"""Tests for per-email login rate limiting on IdentityStrategy (issue #146)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from ninja_auth.config import IdentityConfig
from ninja_auth.errors import AuthenticationError
from ninja_auth.rate_limiter import InMemoryRateLimiter, RateLimitConfig
from ninja_auth.strategies.identity import IdentityStrategy

VALID_PASSWORD = "Password1"
IDENTITY_LOGGER = "ninja_auth.strategies.identity"


def _make_strategy(
    *,
    max_attempts: int = 3,
    window_seconds: int = 60,
    lockout_threshold: int = 3,
    lockout_duration_seconds: int = 300,
    **kwargs: Any,
) -> IdentityStrategy:
    """Create an IdentityStrategy with a tight rate limit for testing."""
    rate_cfg = RateLimitConfig(
        max_attempts=max_attempts,
        window_seconds=window_seconds,
        lockout_threshold=lockout_threshold,
        lockout_duration_seconds=lockout_duration_seconds,
    )
    config = IdentityConfig(
        token_secret="test-secret-key-at-least-32-bytes!!",
        login_rate_limit=rate_cfg,
        **kwargs,
    )
    return IdentityStrategy(config)


def _register(strategy: IdentityStrategy, email: str = "user@example.com") -> None:
    """Register a user with a known password."""
    strategy.register(email, VALID_PASSWORD)


class TestLoginRateLimit:
    """Per-email rate limiting on IdentityStrategy.login()."""

    def test_login_succeeds_within_limit(self) -> None:
        """Logins under the attempt threshold succeed normally."""
        strategy = _make_strategy(max_attempts=5, lockout_threshold=5)
        _register(strategy)

        # 4 failures should still allow another attempt
        for _ in range(4):
            assert strategy.login("user@example.com", "WrongPass1") is None

        ctx = strategy.login("user@example.com", VALID_PASSWORD)
        assert ctx is not None
        assert ctx.email == "user@example.com"

    def test_rate_limited_after_max_attempts(self) -> None:
        """After max_attempts failures, further attempts raise AuthenticationError."""
        strategy = _make_strategy(max_attempts=3, lockout_threshold=3)
        _register(strategy)

        for _ in range(3):
            strategy.login("user@example.com", "WrongPass1")

        with pytest.raises(AuthenticationError, match="Too many login attempts"):
            strategy.login("user@example.com", VALID_PASSWORD)

    def test_rate_limit_is_per_email(self) -> None:
        """Rate limiting is scoped to the email, not global."""
        strategy = _make_strategy(max_attempts=3, lockout_threshold=3)
        _register(strategy, "alice@example.com")
        _register(strategy, "bob@example.com")

        # Exhaust alice's attempts
        for _ in range(3):
            strategy.login("alice@example.com", "WrongPass1")

        with pytest.raises(AuthenticationError):
            strategy.login("alice@example.com", VALID_PASSWORD)

        # Bob is unaffected
        ctx = strategy.login("bob@example.com", VALID_PASSWORD)
        assert ctx is not None
        assert ctx.email == "bob@example.com"

    def test_successful_login_resets_counter(self) -> None:
        """A successful login resets the failure counter for that email."""
        strategy = _make_strategy(max_attempts=5, lockout_threshold=5)
        _register(strategy)

        # 4 failures (one shy of the limit)
        for _ in range(4):
            strategy.login("user@example.com", "WrongPass1")

        # Successful login resets
        ctx = strategy.login("user@example.com", VALID_PASSWORD)
        assert ctx is not None

        # After reset, 4 more failures are allowed
        for _ in range(4):
            strategy.login("user@example.com", "WrongPass1")

        ctx = strategy.login("user@example.com", VALID_PASSWORD)
        assert ctx is not None

    def test_lockout_expires(self) -> None:
        """After the lockout duration, the account is accessible again."""
        strategy = _make_strategy(
            max_attempts=2,
            lockout_threshold=2,
            lockout_duration_seconds=60,
        )
        _register(strategy)

        for _ in range(2):
            strategy.login("user@example.com", "WrongPass1")

        with pytest.raises(AuthenticationError):
            strategy.login("user@example.com", VALID_PASSWORD)

        # Simulate time passing beyond the lockout window
        import time

        bucket = strategy._login_limiter._buckets["user@example.com"]  # type: ignore[attr-defined]
        bucket.locked_until = time.monotonic() - 1
        bucket.attempts.clear()
        bucket.consecutive_failures = 0

        ctx = strategy.login("user@example.com", VALID_PASSWORD)
        assert ctx is not None

    def test_rate_limit_disabled(self) -> None:
        """When rate limiting is disabled, unlimited attempts are allowed."""
        rate_cfg = RateLimitConfig(enabled=False)
        config = IdentityConfig(
            token_secret="test-secret-key-at-least-32-bytes!!",
            login_rate_limit=rate_cfg,
        )
        strategy = IdentityStrategy(config)
        _register(strategy)

        # Many failures should not trigger rate limiting
        for _ in range(50):
            assert strategy.login("user@example.com", "WrongPass1") is None

        ctx = strategy.login("user@example.com", VALID_PASSWORD)
        assert ctx is not None

    def test_rate_limited_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Rate-limited attempts emit a WARNING log entry."""
        strategy = _make_strategy(max_attempts=2, lockout_threshold=2)
        _register(strategy)

        for _ in range(2):
            strategy.login("user@example.com", "WrongPass1")

        with caplog.at_level(logging.WARNING, logger=IDENTITY_LOGGER):
            with pytest.raises(AuthenticationError):
                strategy.login("user@example.com", VALID_PASSWORD)

        rate_limited_records = [r for r in caplog.records if "rate-limited" in r.message.lower()]
        assert len(rate_limited_records) >= 1
        assert "user@example.com" in rate_limited_records[0].message

    def test_unknown_email_counts_toward_limit(self) -> None:
        """Failed attempts for non-existent emails also count."""
        strategy = _make_strategy(max_attempts=3, lockout_threshold=3)

        for _ in range(3):
            strategy.login("ghost@example.com", "WrongPass1")

        with pytest.raises(AuthenticationError, match="Too many login attempts"):
            strategy.login("ghost@example.com", "WrongPass1")

    def test_custom_rate_limiter_injection(self) -> None:
        """A custom RateLimiterProtocol can be injected."""
        rate_cfg = RateLimitConfig(max_attempts=1, lockout_threshold=1)
        custom_limiter = InMemoryRateLimiter(rate_cfg)
        config = IdentityConfig(token_secret="test-secret-key-at-least-32-bytes!!")
        strategy = IdentityStrategy(config, login_rate_limiter=custom_limiter)
        _register(strategy)

        strategy.login("user@example.com", "WrongPass1")

        with pytest.raises(AuthenticationError):
            strategy.login("user@example.com", VALID_PASSWORD)
