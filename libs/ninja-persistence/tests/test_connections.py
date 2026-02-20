"""Tests for connection management."""

import json
import tempfile

import pytest
from ninja_persistence.connections import ConnectionManager, ConnectionProfile


def test_connection_profile_creation():
    profile = ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:")
    assert profile.engine == "sql"
    assert profile.url == "sqlite+aiosqlite:///:memory:"
    assert profile.options == {}


def test_connection_profile_with_options():
    profile = ConnectionProfile(
        engine="sql",
        url="postgresql+asyncpg://localhost/test",
        options={"pool_size": 10, "echo": True},
    )
    assert profile.options["pool_size"] == 10
    assert profile.options["echo"] is True


def test_connection_manager_from_dict():
    profiles = {
        "default": ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:"),
    }
    mgr = ConnectionManager(profiles=profiles)
    profile = mgr.get_profile("default")
    assert profile.url == "sqlite+aiosqlite:///:memory:"


def test_connection_manager_get_profile_missing():
    mgr = ConnectionManager()
    with pytest.raises(KeyError, match="not found"):
        mgr.get_profile("nonexistent")


def test_connection_manager_from_file():
    config = {
        "default": {"engine": "sql", "url": "sqlite+aiosqlite:///:memory:"},
        "mongo": {"engine": "mongo", "url": "mongodb://localhost:27017/test"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        mgr = ConnectionManager.from_file(f.name)

    assert mgr.get_profile("default").engine == "sql"
    assert mgr.get_profile("mongo").engine == "mongo"


def test_connection_manager_from_missing_file():
    mgr = ConnectionManager.from_file("/nonexistent/path/connections.json")
    with pytest.raises(KeyError):
        mgr.get_profile("default")


def test_get_sql_engine():
    profiles = {
        "default": ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:"),
    }
    mgr = ConnectionManager(profiles=profiles)
    engine = mgr.get_sql_engine("default")
    assert engine is not None
    # Should return the same engine on repeated calls
    assert mgr.get_sql_engine("default") is engine


async def test_close_all():
    profiles = {
        "default": ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:"),
    }
    mgr = ConnectionManager(profiles=profiles)
    _ = mgr.get_sql_engine("default")
    await mgr.close_all()
    # After close, getting engine again should create a new one
    engine2 = mgr.get_sql_engine("default")
    assert engine2 is not None
