"""Pluggable rate limiter with in-memory default for authentication endpoints."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RateLimitConfig(BaseModel):
    """Configuration for authentication rate limiting."""

    enabled: bool = True
    max_attempts: int = 10
    window_seconds: int = 60
    lockout_threshold: int = 0  # 0 = disabled; consecutive failures before lockout
    lockout_duration_seconds: int = 300


@runtime_checkable
class RateLimiterProtocol(Protocol):
    """Protocol for pluggable rate limiter implementations.

    Implement this protocol to provide a custom rate limiter (e.g. Redis-backed)
    and pass it to ``AuthConfig`` or ``AuthGateway``.
    """

    def is_rate_limited(self, key: str) -> bool:
        """Return True if *key* should be rejected (429)."""
        ...

    def record_attempt(self, key: str, *, success: bool) -> None:
        """Record an authentication attempt for *key*."""
        ...

    def reset(self, key: str) -> None:
        """Clear all state for *key*."""
        ...


@dataclass
class _BucketState:
    """Tracks attempts and lockout state for a single key (e.g. IP)."""

    attempts: list[float] = field(default_factory=list)
    consecutive_failures: int = 0
    locked_until: float = 0.0


class InMemoryRateLimiter:
    """Sliding-window rate limiter with optional account lockout.

    Keyed by client IP (or any string identifier).  Thread-safe enough for
    single-process async servers; production deployments needing cross-process
    state should swap in a Redis-backed implementation.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._buckets: dict[str, _BucketState] = {}

    def _get_bucket(self, key: str) -> _BucketState:
        if key not in self._buckets:
            self._buckets[key] = _BucketState()
        return self._buckets[key]

    def _prune(self, bucket: _BucketState, now: float) -> None:
        """Remove attempts outside the sliding window."""
        cutoff = now - self.config.window_seconds
        bucket.attempts = [t for t in bucket.attempts if t > cutoff]

    def is_rate_limited(self, key: str) -> bool:
        """Return True if *key* should be rejected (429)."""
        if not self.config.enabled:
            return False

        now = time.monotonic()
        bucket = self._get_bucket(key)

        # Check lockout
        if bucket.locked_until > now:
            return True

        self._prune(bucket, now)
        return len(bucket.attempts) >= self.config.max_attempts

    def record_attempt(self, key: str, *, success: bool) -> None:
        """Record an authentication attempt for *key*."""
        if not self.config.enabled:
            return

        now = time.monotonic()
        bucket = self._get_bucket(key)
        bucket.attempts.append(now)

        if success:
            bucket.consecutive_failures = 0
        else:
            bucket.consecutive_failures += 1
            if self.config.lockout_threshold > 0 and bucket.consecutive_failures >= self.config.lockout_threshold:
                bucket.locked_until = now + self.config.lockout_duration_seconds
                logger.warning(
                    "Account lockout triggered for key=%s after %d consecutive failures",
                    key,
                    bucket.consecutive_failures,
                )

    def reset(self, key: str) -> None:
        """Clear all state for *key* (e.g. after a successful password reset)."""
        self._buckets.pop(key, None)


# Backward-compatible alias
RateLimiter = InMemoryRateLimiter
