"""User store protocol and in-memory implementation for IdentityStrategy."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class UserStore(Protocol):
    """Protocol for pluggable user storage backends.

    Implement this protocol to persist users beyond the default in-memory
    store — e.g. via ``ninja-persistence`` ``Repository`` or any database.
    """

    def get(self, email: str) -> dict[str, Any] | None:
        """Retrieve a user record by email, or ``None`` if not found."""
        ...

    def save(self, email: str, data: dict[str, Any]) -> None:
        """Persist a user record keyed by email."""
        ...

    def exists(self, email: str) -> bool:
        """Return ``True`` if a user with the given email is already stored."""
        ...


class InMemoryUserStore:
    """Non-persistent, in-memory user store for development and testing.

    .. warning::
        All user data is lost on process restart. Do **not** use in production.
        Inject a persistent ``UserStore`` implementation instead.
    """

    def __init__(self) -> None:
        logger.warning(
            "IdentityStrategy is using the in-memory user store. "
            "All user accounts will be lost on restart. "
            "Provide a persistent UserStore implementation for production use.",
        )
        self._users: dict[str, dict[str, Any]] = {}

    def get(self, email: str) -> dict[str, Any] | None:
        return self._users.get(email)

    def save(self, email: str, data: dict[str, Any]) -> None:
        self._users[email] = data

    def exists(self, email: str) -> bool:
        return email in self._users
