"""Token revocation store protocol and in-memory implementation.

Provides server-side token revocation and per-user session invalidation
for JWT-based authentication. The revocation store is opt-in: when not
configured, the auth gateway performs purely stateless JWT validation.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TokenRevocationStore(Protocol):
    """Protocol for pluggable token revocation backends.

    Implement this protocol to back revocation state with Redis, a database,
    or any other persistent store. All methods are async to support I/O-bound
    backends.

    The store tracks two kinds of revocation:

    1. **Per-token revocation** — individual tokens identified by their ``jti``
       claim can be revoked. An optional ``expires_at`` allows the store to
       auto-evict entries after the token's natural expiry.
    2. **Per-user revocation** — all tokens issued before a given timestamp
       for a specific user are considered revoked (useful for password changes
       or security incidents).
    """

    async def revoke_token(self, jti: str, expires_at: datetime | None = None) -> None:
        """Mark a single token as revoked.

        Args:
            jti: The JWT ID claim identifying the token.
            expires_at: Optional expiry time; the store may evict the entry
                after this time since the token would be invalid anyway.
        """
        ...

    async def is_token_revoked(self, jti: str) -> bool:
        """Check whether a token has been individually revoked.

        Args:
            jti: The JWT ID claim to check.

        Returns:
            ``True`` if the token has been revoked, ``False`` otherwise.
        """
        ...

    async def revoke_all_user_tokens(self, user_id: str, before: datetime) -> None:
        """Invalidate all tokens issued to a user before the given timestamp.

        This is typically called after a password change or security incident
        to force re-authentication.

        Args:
            user_id: The user whose tokens should be invalidated.
            before: Tokens with ``iat`` before this timestamp are invalid.
        """
        ...

    async def get_user_revoked_before(self, user_id: str) -> datetime | None:
        """Return the revocation cutoff timestamp for a user.

        Args:
            user_id: The user to look up.

        Returns:
            The cutoff ``datetime`` (UTC), or ``None`` if no per-user
            revocation is active.
        """
        ...


class InMemoryRevocationStore:
    """Non-persistent, in-memory token revocation store for development and testing.

    Stores revoked token JTIs with optional expiry times for automatic cleanup,
    and per-user revocation timestamps. A lazy cleanup pass runs periodically
    to evict expired entries and prevent unbounded memory growth.

    .. warning::
        All revocation state is lost on process restart. Use a persistent
        ``TokenRevocationStore`` implementation (e.g. Redis-backed) in production.

    Args:
        cleanup_interval_seconds: Minimum seconds between lazy cleanup passes.
            Defaults to 60.
    """

    def __init__(self, cleanup_interval_seconds: int = 60) -> None:
        # jti -> expires_at (None means no auto-expiry)
        self._revoked_tokens: dict[str, datetime | None] = {}
        # user_id -> revoked_before timestamp
        self._user_revoked_before: dict[str, datetime] = {}
        self._cleanup_interval = cleanup_interval_seconds
        self._last_cleanup: float = time.monotonic()

    def _maybe_cleanup(self) -> None:
        """Evict expired token revocation entries if the cleanup interval has elapsed."""
        now_mono = time.monotonic()
        if now_mono - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now_mono

        now_utc = datetime.now(timezone.utc)
        expired_jtis = [
            jti
            for jti, exp in self._revoked_tokens.items()
            if exp is not None and exp <= now_utc
        ]
        for jti in expired_jtis:
            del self._revoked_tokens[jti]

        if expired_jtis:
            logger.debug(
                "Revocation store cleanup: evicted %d expired entries", len(expired_jtis)
            )

    async def revoke_token(self, jti: str, expires_at: datetime | None = None) -> None:
        """Mark a single token as revoked.

        Args:
            jti: The JWT ID claim identifying the token.
            expires_at: Optional expiry time for automatic cleanup.
        """
        self._maybe_cleanup()
        self._revoked_tokens[jti] = expires_at

    async def is_token_revoked(self, jti: str) -> bool:
        """Check whether a token has been individually revoked.

        Args:
            jti: The JWT ID claim to check.

        Returns:
            ``True`` if the token is revoked and has not yet been cleaned up.
        """
        self._maybe_cleanup()
        if jti not in self._revoked_tokens:
            return False
        # If it has an expiry and it's passed, treat as not revoked (expired naturally)
        exp = self._revoked_tokens[jti]
        if exp is not None and exp <= datetime.now(timezone.utc):
            del self._revoked_tokens[jti]
            return False
        return True

    async def revoke_all_user_tokens(self, user_id: str, before: datetime) -> None:
        """Invalidate all tokens issued to a user before the given timestamp.

        Args:
            user_id: The user whose tokens should be invalidated.
            before: Tokens with ``iat`` before this timestamp are invalid.
        """
        self._user_revoked_before[user_id] = before

    async def get_user_revoked_before(self, user_id: str) -> datetime | None:
        """Return the revocation cutoff timestamp for a user.

        Args:
            user_id: The user to look up.

        Returns:
            The cutoff ``datetime`` or ``None``.
        """
        return self._user_revoked_before.get(user_id)
