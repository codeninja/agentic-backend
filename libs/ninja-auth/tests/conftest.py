"""Shared fixtures for ninja-auth tests."""

import pytest


@pytest.fixture(autouse=True)
def _ninjastack_dev_env(monkeypatch):
    """Default all auth tests to dev mode so IdentityConfig accepts the default secret."""
    monkeypatch.setenv("NINJASTACK_ENV", "dev")
