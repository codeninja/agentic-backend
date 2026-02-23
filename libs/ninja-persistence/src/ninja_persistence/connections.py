"""Connection pool management — reads config from .ninjastack/connections.json."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ninja_core.security import check_ssrf
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Pattern matches user:password@ in connection URLs.
_CREDENTIAL_RE = re.compile(r"://([^@/]+)@")


def redact_url(url: str) -> str:
    """Replace credentials in a connection URL with ``***:***``.

    >>> redact_url("postgresql+asyncpg://admin:s3cret@db.host:5432/mydb")
    'postgresql+asyncpg://***:***@db.host:5432/mydb'
    >>> redact_url("sqlite+aiosqlite:///:memory:")
    'sqlite+aiosqlite:///:memory:'
    """
    return _CREDENTIAL_RE.sub("://***:***@", url)


class _CredentialRedactFilter(logging.Filter):
    """Logging filter that scrubs credentials from SQLAlchemy log messages."""

    _SCRUB_RE = re.compile(
        r"://[A-Za-z0-9_.~%!$&'()*+,;=:-]+@",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._SCRUB_RE.sub("://***:***@", record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._SCRUB_RE.sub("://***:***@", v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._SCRUB_RE.sub("://***:***@", a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


class InvalidConnectionURL(ValueError):
    """Raised when a connection URL is malformed or missing required components."""


class ConnectionProfile(BaseModel):
    """A single database connection configuration."""

    engine: str = Field(description="Storage engine type: sql, mongo, graph, vector.")
    url: str = Field(description="Connection URL / DSN.")
    options: dict[str, Any] = Field(default_factory=dict, description="Engine-specific options.")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str, info: ValidationInfo) -> str:
        """Validate the connection URL has required components and is not targeting private hosts.

        Pass ``context={"allow_private_hosts": True}`` via
        :meth:`model_validate` to skip the SSRF check (local dev only).
        """
        parsed = urlparse(v)
        scheme = parsed.scheme.split("+")[0]  # e.g. "sqlite+aiosqlite" -> "sqlite"

        if scheme == "sqlite":
            # sqlite:///:memory: is valid (path = "/:memory:")
            # sqlite:///path/to/db.sqlite is valid
            # sqlite:/// (empty path after authority) is NOT valid
            db_path = parsed.path
            if not db_path or db_path == "/":
                raise InvalidConnectionURL(
                    f"Invalid SQLite URL '{v}': missing database path. "
                    "Use 'sqlite:////absolute/path.db', 'sqlite:///relative.db', "
                    "or 'sqlite:///:memory:' for an in-memory database."
                )
        elif scheme in ("postgresql", "postgres", "mysql", "mariadb"):
            if not parsed.hostname:
                raise InvalidConnectionURL(
                    f"Invalid database URL '{v}': missing hostname. "
                    f"Expected format: '{scheme}://user:pass@host:port/dbname'"
                )
            if not parsed.path or parsed.path == "/":
                raise InvalidConnectionURL(
                    f"Invalid database URL '{v}': missing database name. "
                    f"Expected format: '{scheme}://user:pass@host:port/dbname'"
                )
        elif scheme in ("mongodb", "mongodb+srv"):
            if not parsed.hostname:
                raise InvalidConnectionURL(
                    f"Invalid MongoDB URL '{v}': missing hostname. Expected format: 'mongodb://host:port/dbname'"
                )

        # SSRF protection — block private/reserved IP ranges.
        # allow_private_hosts can be set via Pydantic validation context.
        allow_private = (info.context or {}).get("allow_private_hosts", False) if info else False
        ssrf_error = check_ssrf(v, allow_private_hosts=allow_private)
        if ssrf_error:
            raise InvalidConnectionURL(ssrf_error)

        return v


class ConnectionManager:
    """Manages connection pools for all configured engines.

    Reads connection profiles from `.ninjastack/connections.json` and lazily
    creates engine-specific connection objects on first access.
    """

    def __init__(self, profiles: dict[str, ConnectionProfile] | None = None) -> None:
        self._profiles: dict[str, ConnectionProfile] = profiles or {}
        self._sql_engines: dict[str, AsyncEngine] = {}

    @classmethod
    def from_file(cls, path: str | Path = ".ninjastack/connections.json") -> ConnectionManager:
        """Load connection profiles from a JSON file."""
        filepath = Path(path)
        if not filepath.exists():
            return cls(profiles={})
        raw = json.loads(filepath.read_text())
        profiles = {name: ConnectionProfile(**cfg) for name, cfg in raw.items()}
        return cls(profiles=profiles)

    def get_profile(self, name: str) -> ConnectionProfile:
        """Get a connection profile by name."""
        if name not in self._profiles:
            raise KeyError(f"Connection profile '{name}' not found. Available: {list(self._profiles.keys())}")
        return self._profiles[name]

    def get_sql_engine(self, profile_name: str = "default") -> AsyncEngine:
        """Get or create an async SQLAlchemy engine for the given profile."""
        if profile_name not in self._sql_engines:
            profile = self.get_profile(profile_name)
            echo = profile.options.get("echo", False)
            kwargs: dict[str, Any] = {"echo": echo}
            # pool_size/max_overflow are not supported by SQLite's StaticPool
            if not profile.url.startswith("sqlite"):
                kwargs["pool_size"] = profile.options.get("pool_size", 5)
                kwargs["max_overflow"] = profile.options.get("max_overflow", 10)
            engine = create_async_engine(profile.url, **kwargs)
            if echo:
                _install_credential_filter(engine)
            self._sql_engines[profile_name] = engine
        return self._sql_engines[profile_name]

    async def close_all(self) -> None:
        """Dispose all managed connection pools."""
        for engine in self._sql_engines.values():
            await engine.dispose()
        self._sql_engines.clear()


def _install_credential_filter(engine: AsyncEngine) -> None:
    """Attach :class:`_CredentialRedactFilter` to every logger used by *engine*."""
    filt = _CredentialRedactFilter()
    for name in (
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        f"sqlalchemy.engine.Engine.{engine.sync_engine.logging_name or ''}",
    ):
        logging.getLogger(name).addFilter(filt)
