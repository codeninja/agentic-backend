"""Tests for the rate limiter module."""

import time
from unittest.mock import patch

from ninja_auth.rate_limiter import InMemoryRateLimiter, RateLimitConfig, RateLimiter, RateLimiterProtocol


def _make_limiter(**kwargs) -> RateLimiter:
    return RateLimiter(RateLimitConfig(**kwargs))


def test_allows_requests_under_limit():
    limiter = _make_limiter(max_attempts=5, window_seconds=60)
    for _ in range(4):
        assert not limiter.is_rate_limited("1.2.3.4")
        limiter.record_attempt("1.2.3.4", success=False)
    assert not limiter.is_rate_limited("1.2.3.4")


def test_blocks_after_max_attempts():
    limiter = _make_limiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        limiter.record_attempt("1.2.3.4", success=False)
    assert limiter.is_rate_limited("1.2.3.4")


def test_successful_attempts_also_count():
    """Successful auth still counts toward the sliding window to prevent enumeration."""
    limiter = _make_limiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        limiter.record_attempt("1.2.3.4", success=True)
    assert limiter.is_rate_limited("1.2.3.4")


def test_window_expiry_allows_new_attempts():
    limiter = _make_limiter(max_attempts=2, window_seconds=1)
    limiter.record_attempt("1.2.3.4", success=False)
    limiter.record_attempt("1.2.3.4", success=False)
    assert limiter.is_rate_limited("1.2.3.4")

    # Simulate time passing beyond the window
    with patch("ninja_auth.rate_limiter.time") as mock_time:
        mock_time.monotonic.return_value = time.monotonic() + 2
        assert not limiter.is_rate_limited("1.2.3.4")


def test_different_keys_are_independent():
    limiter = _make_limiter(max_attempts=2, window_seconds=60)
    limiter.record_attempt("1.1.1.1", success=False)
    limiter.record_attempt("1.1.1.1", success=False)
    assert limiter.is_rate_limited("1.1.1.1")
    assert not limiter.is_rate_limited("2.2.2.2")


def test_lockout_after_consecutive_failures():
    limiter = _make_limiter(
        max_attempts=100,  # high limit so we hit lockout first
        window_seconds=60,
        lockout_threshold=3,
        lockout_duration_seconds=300,
    )
    for _ in range(3):
        limiter.record_attempt("1.2.3.4", success=False)
    assert limiter.is_rate_limited("1.2.3.4")


def test_success_resets_consecutive_failures():
    limiter = _make_limiter(
        max_attempts=100,
        window_seconds=60,
        lockout_threshold=3,
        lockout_duration_seconds=300,
    )
    limiter.record_attempt("1.2.3.4", success=False)
    limiter.record_attempt("1.2.3.4", success=False)
    limiter.record_attempt("1.2.3.4", success=True)  # resets consecutive count
    limiter.record_attempt("1.2.3.4", success=False)
    limiter.record_attempt("1.2.3.4", success=False)
    assert not limiter.is_rate_limited("1.2.3.4")


def test_disabled_limiter_allows_everything():
    limiter = _make_limiter(enabled=False, max_attempts=1)
    limiter.record_attempt("1.2.3.4", success=False)
    limiter.record_attempt("1.2.3.4", success=False)
    assert not limiter.is_rate_limited("1.2.3.4")


def test_reset_clears_state():
    limiter = _make_limiter(max_attempts=1, window_seconds=60)
    limiter.record_attempt("1.2.3.4", success=False)
    assert limiter.is_rate_limited("1.2.3.4")
    limiter.reset("1.2.3.4")
    assert not limiter.is_rate_limited("1.2.3.4")


def test_in_memory_satisfies_protocol():
    """InMemoryRateLimiter satisfies the RateLimiterProtocol."""
    limiter = InMemoryRateLimiter(RateLimitConfig())
    assert isinstance(limiter, RateLimiterProtocol)


def test_backward_compat_alias():
    """RateLimiter is an alias for InMemoryRateLimiter."""
    assert RateLimiter is InMemoryRateLimiter


def test_custom_rate_limiter_protocol():
    """A custom class satisfying RateLimiterProtocol is recognized."""

    class CustomLimiter:
        def is_rate_limited(self, key: str) -> bool:
            return key == "blocked"

        def record_attempt(self, key: str, *, success: bool) -> None:
            pass

        def reset(self, key: str) -> None:
            pass

    limiter = CustomLimiter()
    assert isinstance(limiter, RateLimiterProtocol)
    assert limiter.is_rate_limited("blocked")
    assert not limiter.is_rate_limited("allowed")
