"""Tests for connection management."""

import json
import logging
import tempfile
from unittest.mock import patch

import pytest
from ninja_persistence.connections import (
    ConnectionManager,
    ConnectionProfile,
    _CredentialRedactFilter,
    redact_url,
)
from pydantic import ValidationError


# Helper to create profiles with localhost URLs (which require allow_private_hosts).
def _profile_local(**kwargs):
    """Create a ConnectionProfile with SSRF checks disabled for localhost URLs."""
    return ConnectionProfile.model_validate(kwargs, context={"allow_private_hosts": True})


def test_connection_profile_creation():
    profile = ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:")
    assert profile.engine == "sql"
    assert profile.url == "sqlite+aiosqlite:///:memory:"
    assert profile.options == {}


def test_connection_profile_with_options():
    profile = _profile_local(
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
        # from_file uses ConnectionProfile(**cfg) which doesn't pass context,
        # so we mock DNS resolution for localhost URLs
        with patch("ninja_core.security.socket.getaddrinfo", side_effect=OSError("mocked")):
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


# --- URL Validation Tests ---


class TestURLValidation:
    """Tests for connection URL validation (issue #48)."""

    def test_sqlite_empty_path_rejected(self):
        with pytest.raises(ValidationError, match="missing database path"):
            ConnectionProfile(engine="sql", url="sqlite:///")

    def test_sqlite_aiosqlite_empty_path_rejected(self):
        with pytest.raises(ValidationError, match="missing database path"):
            ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///")

    def test_sqlite_memory_accepted(self):
        p = ConnectionProfile(engine="sql", url="sqlite:///:memory:")
        assert ":memory:" in p.url

    def test_sqlite_aiosqlite_memory_accepted(self):
        p = ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:")
        assert ":memory:" in p.url

    def test_sqlite_file_path_accepted(self):
        p = ConnectionProfile(engine="sql", url="sqlite:///tmp/test.db")
        assert p.url == "sqlite:///tmp/test.db"

    def test_sqlite_absolute_path_accepted(self):
        p = ConnectionProfile(engine="sql", url="sqlite:////absolute/path/db.sqlite")
        assert p.url == "sqlite:////absolute/path/db.sqlite"

    def test_postgres_missing_host_rejected(self):
        with pytest.raises(ValidationError, match="missing hostname"):
            ConnectionProfile(engine="sql", url="postgresql:///dbname")

    def test_postgres_missing_dbname_rejected(self):
        with pytest.raises(ValidationError, match="missing database name"):
            _profile_local(engine="sql", url="postgresql://localhost/")

    def test_postgres_valid_accepted(self):
        p = _profile_local(engine="sql", url="postgresql+asyncpg://user:pass@localhost:5432/mydb")
        assert "mydb" in p.url

    def test_mongodb_missing_host_rejected(self):
        with pytest.raises(ValidationError, match="missing hostname"):
            ConnectionProfile(engine="mongo", url="mongodb:///")

    def test_mongodb_valid_accepted(self):
        p = _profile_local(engine="mongo", url="mongodb://localhost:27017/test")
        assert "localhost" in p.url

    def test_mysql_missing_host_rejected(self):
        with pytest.raises(ValidationError, match="missing hostname"):
            ConnectionProfile(engine="sql", url="mysql:///dbname")

    def test_unknown_scheme_passes(self):
        """Unknown schemes should not be rejected — extensibility."""
        p = _profile_local(engine="graph", url="neo4j://localhost:7687")
        assert p.url == "neo4j://localhost:7687"

    def test_validation_error_message_is_actionable(self):
        with pytest.raises(ValidationError) as exc_info:
            ConnectionProfile(engine="sql", url="sqlite:///")
        msg = str(exc_info.value)
        assert "sqlite:///:memory:" in msg
        assert "sqlite:///relative.db" in msg or "sqlite:////absolute" in msg


class TestSSRFProtection:
    """Tests for SSRF protection in ConnectionProfile URL validation."""

    def test_blocks_private_ip(self):
        with pytest.raises(ValidationError, match="private/reserved range"):
            ConnectionProfile(engine="sql", url="postgresql://10.0.0.1:5432/db")

    def test_blocks_loopback_ip(self):
        with pytest.raises(ValidationError, match="private/reserved range"):
            ConnectionProfile(engine="sql", url="postgresql://127.0.0.1:5432/db")

    def test_blocks_link_local_ip(self):
        with pytest.raises(ValidationError, match="private/reserved range"):
            ConnectionProfile(engine="sql", url="http://169.254.169.254/meta")

    def test_allows_with_context_override(self):
        """allow_private_hosts via validation context skips SSRF checks."""
        p = ConnectionProfile.model_validate(
            {"engine": "sql", "url": "postgresql://10.0.0.1:5432/db"},
            context={"allow_private_hosts": True},
        )
        assert "10.0.0.1" in p.url

    @patch("ninja_core.security.socket.getaddrinfo")
    def test_blocks_hostname_resolving_to_private(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("192.168.1.50", 5432)),
        ]
        with pytest.raises(ValidationError, match="private/reserved range"):
            ConnectionProfile(engine="sql", url="postgresql://db.internal:5432/mydb")

    def test_allows_public_ip(self):
        p = ConnectionProfile(engine="sql", url="postgresql://203.0.113.10:5432/db")
        assert p.url == "postgresql://203.0.113.10:5432/db"


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


class TestCredentialRedaction:
    """Tests for credential redaction from connection URLs (issue #122)."""

    def test_redact_url_with_user_and_password(self):
        url = "postgresql+asyncpg://admin:s3cret@db.host:5432/mydb"
        assert redact_url(url) == "postgresql+asyncpg://***:***@db.host:5432/mydb"

    def test_redact_url_with_user_only(self):
        url = "postgresql+asyncpg://admin@db.host:5432/mydb"
        assert redact_url(url) == "postgresql+asyncpg://***:***@db.host:5432/mydb"

    def test_redact_url_no_credentials(self):
        url = "sqlite+aiosqlite:///:memory:"
        assert redact_url(url) == "sqlite+aiosqlite:///:memory:"

    def test_redact_url_special_chars_in_password(self):
        url = "postgresql://user:p%40ss%3Dw0rd@host/db"
        assert redact_url(url) == "postgresql://***:***@host/db"

    def test_redact_url_mongodb(self):
        url = "mongodb://root:topsecret@mongo.internal:27017/app"
        assert redact_url(url) == "mongodb://***:***@mongo.internal:27017/app"

    def test_filter_scrubs_log_message(self):
        filt = _CredentialRedactFilter()
        record = logging.LogRecord(
            name="sqlalchemy.engine",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting to postgresql://admin:secret@db:5432/mydb",
            args=None,
            exc_info=None,
        )
        filt.filter(record)
        assert "secret" not in record.msg
        assert "***:***@db:5432" in record.msg

    def test_filter_scrubs_tuple_args(self):
        filt = _CredentialRedactFilter()
        record = logging.LogRecord(
            name="sqlalchemy.pool",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Pool %s",
            args=("postgresql://user:pass@host/db",),
            exc_info=None,
        )
        filt.filter(record)
        assert "pass" not in record.args[0]
        assert "***:***@host" in record.args[0]

    def test_filter_scrubs_dict_args(self):
        filt = _CredentialRedactFilter()
        record = logging.LogRecord(
            name="sqlalchemy.engine",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="%(url)s",
            args=None,
            exc_info=None,
        )
        # Set dict args after construction to avoid LogRecord __init__ issue
        record.args = {"url": "mysql://root:secret@db/app"}
        filt.filter(record)
        assert "secret" not in record.args["url"]
        assert "***:***@db" in record.args["url"]

    def test_echo_engine_installs_filter(self):
        """When echo=True, the credential filter is installed on SQLAlchemy loggers."""
        profiles = {
            "default": _profile_local(
                engine="sql",
                url="sqlite+aiosqlite:///:memory:",
                options={"echo": True},
            ),
        }
        mgr = ConnectionManager(profiles=profiles)
        mgr.get_sql_engine("default")

        sa_logger = logging.getLogger("sqlalchemy.engine")
        filter_types = [type(f) for f in sa_logger.filters]
        assert _CredentialRedactFilter in filter_types

    def test_no_filter_when_echo_disabled(self):
        """When echo is not set, no filter should be installed."""
        profiles = {
            "default": ConnectionProfile(engine="sql", url="sqlite+aiosqlite:///:memory:"),
        }
        mgr = ConnectionManager(profiles=profiles)

        # Clear any existing filters first
        sa_logger = logging.getLogger("sqlalchemy.engine")
        original_filters = sa_logger.filters[:]

        mgr.get_sql_engine("default")

        new_filters = [f for f in sa_logger.filters if f not in original_filters]
        assert not any(isinstance(f, _CredentialRedactFilter) for f in new_filters)
