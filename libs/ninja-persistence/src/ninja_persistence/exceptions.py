"""Domain exceptions for the persistence layer.

All adapter-specific driver exceptions are caught and re-raised as one of these
domain exceptions so that upstream callers never see raw database errors.
"""

from __future__ import annotations


class PersistenceError(Exception):
    """Base exception for all persistence-layer errors.

    Attributes:
        entity_name: The name of the entity/collection involved.
        operation: The CRUD operation that failed (e.g. ``"create"``, ``"find_by_id"``).
        detail: A sanitised description of what went wrong.
    """

    def __init__(
        self,
        *,
        entity_name: str,
        operation: str,
        detail: str,
        cause: Exception | None = None,
    ) -> None:
        self.entity_name = entity_name
        self.operation = operation
        self.detail = detail
        msg = f"[{entity_name}] {operation} failed: {detail}"
        super().__init__(msg)
        if cause is not None:
            self.__cause__ = cause


class DuplicateEntityError(PersistenceError):
    """Raised when an insert violates a uniqueness constraint."""


class EntityNotFoundError(PersistenceError):
    """Raised when an expected record does not exist."""


class ConnectionFailedError(PersistenceError):
    """Raised when the adapter cannot reach the database."""


class QueryError(PersistenceError):
    """Raised for invalid queries, bad filter expressions, or schema mismatches."""


class TransactionError(PersistenceError):
    """Raised when a transaction fails to commit or rollback."""
