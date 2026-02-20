"""Connection pool management — reads config from .ninjastack/connections.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class ConnectionProfile(BaseModel):
    """A single database connection configuration."""

    engine: str = Field(description="Storage engine type: sql, mongo, graph, vector.")
    url: str = Field(description="Connection URL / DSN.")
    options: dict[str, Any] = Field(default_factory=dict, description="Engine-specific options.")


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
            kwargs: dict[str, Any] = {"echo": profile.options.get("echo", False)}
            # pool_size/max_overflow are not supported by SQLite's StaticPool
            if not profile.url.startswith("sqlite"):
                kwargs["pool_size"] = profile.options.get("pool_size", 5)
                kwargs["max_overflow"] = profile.options.get("max_overflow", 10)
            self._sql_engines[profile_name] = create_async_engine(profile.url, **kwargs)
        return self._sql_engines[profile_name]

    async def close_all(self) -> None:
        """Dispose all managed connection pools."""
        for engine in self._sql_engines.values():
            await engine.dispose()
        self._sql_engines.clear()
