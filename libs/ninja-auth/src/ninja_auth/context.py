"""User context model injected into agent request chain."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_serializer

_SENSITIVE_PATTERN = re.compile(
    r"(password|secret|token|api_key|access_token|refresh_token|credential)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


class UserContext(BaseModel):
    """Authenticated user identity available throughout the request lifecycle."""

    user_id: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    provider: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Sensitive — excluded from serialization by default
    _access_token: str = ""

    def __init__(self, _access_token: str = "", **data: Any) -> None:
        super().__init__(**data)
        self._access_token = _access_token

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def is_authenticated(self) -> bool:
        return bool(self.user_id)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    @staticmethod
    def _redact_dict(d: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *d* with sensitive keys masked."""
        result: dict[str, Any] = {}
        for key, value in d.items():
            if _SENSITIVE_PATTERN.search(key):
                result[key] = _REDACTED
            elif isinstance(value, dict):
                result[key] = UserContext._redact_dict(value)
            else:
                result[key] = value
        return result

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "roles": list(self.roles),
            "permissions": list(self.permissions),
            "provider": self.provider,
            "metadata": self._redact_dict(self.metadata),
        }

    def __repr__(self) -> str:
        return (
            f"UserContext(user_id={self.user_id!r}, email={self.email!r}, "
            f"provider={self.provider!r}, roles={self.roles!r})"
        )


ANONYMOUS_USER = UserContext(user_id="", provider="anonymous")
