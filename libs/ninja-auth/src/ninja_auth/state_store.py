"""OAuth2 state storage protocol and in-memory implementation."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OAuthStateStore(Protocol):
    """Protocol for storing and retrieving OAuth2 CSRF state tokens.

    Implementations must handle TTL-based expiration so stale state tokens
    are automatically cleaned up.
    """

    async def save_state(self, state: str, metadata: dict[str, Any], *, ttl_seconds: int = 300) -> None:
        """Persist an OAuth2 state token with associated metadata.

        Args:
            state: The cryptographic state token generated during authorization.
            metadata: Arbitrary data to associate with the state (e.g. provider name,
                redirect target, nonce).
            ttl_seconds: Time-to-live in seconds. The entry should be automatically
                discarded after this period.
        """
        ...

    async def get_state(self, state: str) -> dict[str, Any] | None:
        """Retrieve metadata for a state token, returning ``None`` if expired or missing.

        Args:
            state: The state token to look up.

        Returns:
            The metadata dict stored alongside the token, or ``None`` if the
            token does not exist or has expired.
        """
        ...

    async def delete_state(self, state: str) -> None:
        """Remove a state token from the store.

        This should be called after successful validation to prevent replay.

        Args:
            state: The state token to delete.
        """
        ...


class InMemoryOAuthStateStore:
    """In-memory implementation of :class:`OAuthStateStore` with TTL expiration.

    Suitable for development and single-process deployments. Production systems
    should use a Redis or database-backed implementation for multi-process safety.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[dict[str, Any], float]] = {}
        self._lock = asyncio.Lock()

    async def save_state(self, state: str, metadata: dict[str, Any], *, ttl_seconds: int = 300) -> None:
        """Save a state token with metadata and expiration timestamp."""
        expires_at = time.monotonic() + ttl_seconds
        async with self._lock:
            self._store[state] = (metadata, expires_at)

    async def get_state(self, state: str) -> dict[str, Any] | None:
        """Retrieve state metadata if the token exists and has not expired."""
        async with self._lock:
            entry = self._store.get(state)
            if entry is None:
                return None
            metadata, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[state]
                return None
            return metadata

    async def delete_state(self, state: str) -> None:
        """Delete a state token from the store."""
        async with self._lock:
            self._store.pop(state, None)

    async def _purge_expired(self) -> int:
        """Remove all expired entries and return the count of purged items.

        This is exposed for testing and optional periodic cleanup.
        """
        now = time.monotonic()
        purged = 0
        async with self._lock:
            expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
            for key in expired_keys:
                del self._store[key]
                purged += 1
        return purged
