"""Tests for the persistence domain exceptions module."""

from ninja_persistence.exceptions import (
    ConnectionFailedError,
    DuplicateEntityError,
    EntityNotFoundError,
    PersistenceError,
    QueryError,
    TransactionError,
)


def test_persistence_error_message():
    """PersistenceError formats entity, operation and detail into message."""
    exc = PersistenceError(entity_name="User", operation="create", detail="something broke")
    assert "[User] create failed: something broke" in str(exc)
    assert exc.entity_name == "User"
    assert exc.operation == "create"
    assert exc.detail == "something broke"


def test_persistence_error_with_cause():
    """PersistenceError chains the original cause."""
    cause = ValueError("original")
    exc = PersistenceError(entity_name="User", operation="create", detail="wrapped", cause=cause)
    assert exc.__cause__ is cause


def test_duplicate_entity_error_is_persistence_error():
    """DuplicateEntityError inherits from PersistenceError."""
    exc = DuplicateEntityError(entity_name="User", operation="create", detail="dup")
    assert isinstance(exc, PersistenceError)


def test_entity_not_found_error_is_persistence_error():
    """EntityNotFoundError inherits from PersistenceError."""
    exc = EntityNotFoundError(entity_name="User", operation="find_by_id", detail="missing")
    assert isinstance(exc, PersistenceError)


def test_connection_failed_error_is_persistence_error():
    """ConnectionFailedError inherits from PersistenceError."""
    exc = ConnectionFailedError(entity_name="User", operation="find_by_id", detail="timeout")
    assert isinstance(exc, PersistenceError)


def test_query_error_is_persistence_error():
    """QueryError inherits from PersistenceError."""
    exc = QueryError(entity_name="User", operation="find_many", detail="bad filter")
    assert isinstance(exc, PersistenceError)


def test_transaction_error_is_persistence_error():
    """TransactionError inherits from PersistenceError."""
    exc = TransactionError(entity_name="User", operation="create", detail="commit failed")
    assert isinstance(exc, PersistenceError)
