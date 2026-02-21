"""Tests for OAuthStateStore protocol and InMemoryOAuthStateStore."""

import asyncio
import time
from unittest.mock import patch

import pytest

from ninja_auth.state_store import InMemoryOAuthStateStore, OAuthStateStore


@pytest.fixture
def store() -> InMemoryOAuthStateStore:
    return InMemoryOAuthStateStore()


async def test_save_and_get_state(store: InMemoryOAuthStateStore):
    """Saved state should be retrievable."""
    await store.save_state("tok-1", {"provider": "google"})
    result = await store.get_state("tok-1")
    assert result == {"provider": "google"}


async def test_get_nonexistent_state_returns_none(store: InMemoryOAuthStateStore):
    """Looking up a missing state should return None."""
    result = await store.get_state("nonexistent")
    assert result is None


async def test_delete_state(store: InMemoryOAuthStateStore):
    """Deleted state should no longer be retrievable."""
    await store.save_state("tok-del", {"provider": "github"})
    await store.delete_state("tok-del")
    result = await store.get_state("tok-del")
    assert result is None


async def test_delete_nonexistent_state_is_noop(store: InMemoryOAuthStateStore):
    """Deleting a missing state should not raise."""
    await store.delete_state("missing")


async def test_ttl_expiration(store: InMemoryOAuthStateStore):
    """State should expire after TTL elapses."""
    await store.save_state("tok-exp", {"provider": "google"}, ttl_seconds=1)

    # Should be available immediately
    result = await store.get_state("tok-exp")
    assert result is not None

    # Simulate time passing beyond TTL
    with patch("ninja_auth.state_store.time.monotonic", return_value=time.monotonic() + 2):
        result = await store.get_state("tok-exp")
        assert result is None


async def test_ttl_not_expired_yet(store: InMemoryOAuthStateStore):
    """State should still be available before TTL expires."""
    await store.save_state("tok-fresh", {"provider": "github"}, ttl_seconds=300)
    result = await store.get_state("tok-fresh")
    assert result == {"provider": "github"}


async def test_overwrite_state(store: InMemoryOAuthStateStore):
    """Saving to the same key should overwrite the previous entry."""
    await store.save_state("tok-ow", {"v": 1})
    await store.save_state("tok-ow", {"v": 2})
    result = await store.get_state("tok-ow")
    assert result == {"v": 2}


async def test_purge_expired(store: InMemoryOAuthStateStore):
    """_purge_expired should remove expired entries."""
    await store.save_state("a", {"x": 1}, ttl_seconds=1)
    await store.save_state("b", {"x": 2}, ttl_seconds=1)
    await store.save_state("c", {"x": 3}, ttl_seconds=600)

    with patch("ninja_auth.state_store.time.monotonic", return_value=time.monotonic() + 2):
        purged = await store._purge_expired()
        assert purged == 2

    # "c" should still be available (not expired)
    result = await store.get_state("c")
    assert result == {"x": 3}


async def test_multiple_states_independent(store: InMemoryOAuthStateStore):
    """Multiple states should be independently retrievable and deletable."""
    await store.save_state("s1", {"p": "google"})
    await store.save_state("s2", {"p": "github"})

    assert (await store.get_state("s1")) == {"p": "google"}
    assert (await store.get_state("s2")) == {"p": "github"}

    await store.delete_state("s1")
    assert (await store.get_state("s1")) is None
    assert (await store.get_state("s2")) == {"p": "github"}


def test_protocol_compliance():
    """InMemoryOAuthStateStore should satisfy the OAuthStateStore protocol."""
    assert isinstance(InMemoryOAuthStateStore(), OAuthStateStore)
