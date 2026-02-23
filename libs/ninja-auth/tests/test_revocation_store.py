"""Unit tests for InMemoryRevocationStore."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from ninja_auth.revocation import InMemoryRevocationStore, TokenRevocationStore


@pytest.fixture
def store() -> InMemoryRevocationStore:
    return InMemoryRevocationStore(cleanup_interval_seconds=0)


def _run(coro):
    """Helper to run async coroutines in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestTokenRevocationStoreProtocol:
    """Verify InMemoryRevocationStore satisfies the TokenRevocationStore protocol."""

    def test_protocol_compliance(self) -> None:
        assert isinstance(InMemoryRevocationStore(), TokenRevocationStore)


class TestRevokeAndCheckToken:
    """Per-token revocation via jti."""

    def test_token_not_revoked_by_default(self, store: InMemoryRevocationStore) -> None:
        assert _run(store.is_token_revoked("some-jti")) is False

    def test_revoke_token_makes_it_revoked(self, store: InMemoryRevocationStore) -> None:
        _run(store.revoke_token("jti-1"))
        assert _run(store.is_token_revoked("jti-1")) is True

    def test_revoke_does_not_affect_other_tokens(self, store: InMemoryRevocationStore) -> None:
        _run(store.revoke_token("jti-1"))
        assert _run(store.is_token_revoked("jti-2")) is False

    def test_revoke_with_future_expiry(self, store: InMemoryRevocationStore) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _run(store.revoke_token("jti-exp", expires_at=future))
        assert _run(store.is_token_revoked("jti-exp")) is True

    def test_revoke_with_past_expiry_auto_cleans(self, store: InMemoryRevocationStore) -> None:
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        _run(store.revoke_token("jti-old", expires_at=past))
        # Token expired — should no longer be considered revoked
        assert _run(store.is_token_revoked("jti-old")) is False

    def test_revoke_without_expiry_persists(self, store: InMemoryRevocationStore) -> None:
        _run(store.revoke_token("jti-forever"))
        assert _run(store.is_token_revoked("jti-forever")) is True


class TestPerUserRevocation:
    """Per-user revocation via revoked_before timestamp."""

    def test_no_user_revocation_by_default(self, store: InMemoryRevocationStore) -> None:
        result = _run(store.get_user_revoked_before("user-1"))
        assert result is None

    def test_revoke_all_user_tokens(self, store: InMemoryRevocationStore) -> None:
        cutoff = datetime.now(timezone.utc)
        _run(store.revoke_all_user_tokens("user-1", before=cutoff))
        result = _run(store.get_user_revoked_before("user-1"))
        assert result == cutoff

    def test_revoke_does_not_affect_other_users(self, store: InMemoryRevocationStore) -> None:
        cutoff = datetime.now(timezone.utc)
        _run(store.revoke_all_user_tokens("user-1", before=cutoff))
        assert _run(store.get_user_revoked_before("user-2")) is None

    def test_revoke_updates_timestamp(self, store: InMemoryRevocationStore) -> None:
        first = datetime(2024, 1, 1, tzinfo=timezone.utc)
        second = datetime(2024, 6, 1, tzinfo=timezone.utc)
        _run(store.revoke_all_user_tokens("user-1", before=first))
        _run(store.revoke_all_user_tokens("user-1", before=second))
        result = _run(store.get_user_revoked_before("user-1"))
        assert result == second


class TestCleanup:
    """TTL-based cleanup of expired entries."""

    def test_cleanup_evicts_expired_entries(self) -> None:
        store = InMemoryRevocationStore(cleanup_interval_seconds=0)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        _run(store.revoke_token("expired-jti", expires_at=past))
        _run(store.revoke_token("valid-jti", expires_at=future))

        # The expired one should be cleaned up on next access
        assert _run(store.is_token_revoked("expired-jti")) is False
        assert _run(store.is_token_revoked("valid-jti")) is True

    def test_cleanup_skipped_when_interval_not_elapsed(self) -> None:
        store = InMemoryRevocationStore(cleanup_interval_seconds=9999)
        past = datetime.now(timezone.utc) - timedelta(hours=1)

        # Manually insert an expired entry
        store._revoked_tokens["old-jti"] = past

        # is_token_revoked still catches expired entries individually
        assert _run(store.is_token_revoked("old-jti")) is False
