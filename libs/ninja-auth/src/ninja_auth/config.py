"""Auth configuration loaded from .ninjastack/auth.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ninja_auth.rbac import RBACConfig


class OAuth2ProviderConfig(BaseModel):
    """Configuration for a single OAuth2 provider."""

    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    redirect_uri: str = ""


class BearerConfig(BaseModel):
    """JWT bearer token validation config."""

    algorithm: str = "HS256"
    secret_key: str = ""
    public_key: str = ""
    issuer: str = ""
    audience: str = ""


class ApiKeyConfig(BaseModel):
    """API key strategy configuration."""

    header_name: str = "X-API-Key"
    keys: dict[str, str] = Field(default_factory=dict)


class IdentityConfig(BaseModel):
    """Built-in identity (registration/login) config."""

    enabled: bool = True
    hash_algorithm: str = "bcrypt"
    token_secret: str = "change-me-in-production"
    token_expiry_minutes: int = 60


class AuthConfig(BaseModel):
    """Top-level auth configuration."""

    default_strategy: str = "bearer"
    public_paths: list[str] = Field(default_factory=lambda: ["/health", "/docs", "/openapi.json"])
    oauth2_providers: dict[str, OAuth2ProviderConfig] = Field(default_factory=dict)
    bearer: BearerConfig = Field(default_factory=BearerConfig)
    api_key: ApiKeyConfig = Field(default_factory=ApiKeyConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    rbac: RBACConfig = Field(default_factory=RBACConfig)

    @classmethod
    def from_file(cls, path: str | Path = ".ninjastack/auth.json") -> AuthConfig:
        """Load config from a JSON file, falling back to defaults."""
        p = Path(path)
        if p.exists():
            data: dict[str, Any] = json.loads(p.read_text())
            return cls.model_validate(data)
        return cls()
