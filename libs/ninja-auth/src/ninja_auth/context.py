"""User context model injected into agent request chain."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Authenticated user identity available throughout the request lifecycle."""

    user_id: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    provider: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return bool(self.user_id)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


ANONYMOUS_USER = UserContext(user_id="", provider="anonymous")
