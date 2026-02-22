"""Auth configuration loaded from .ninjastack/auth.json."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ninja_auth.rate_limiter import RateLimitConfig
from ninja_auth.rbac import RBACConfig

logger = logging.getLogger(__name__)

# Prefix constants for key storage formats
_HASH_PREFIX = "sha256:"
_ENV_PREFIX = "$env:"


class OAuth2ProviderConfig(BaseModel):
    """Configuration for a single OAuth2 provider."""

    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    redirect_uri: str = ""

    @model_validator(mode="after")
    def _check_redirect_uri(self) -> OAuth2ProviderConfig:
        if not self.redirect_uri:
            return self
        from urllib.parse import urlparse

        parsed = urlparse(self.redirect_uri)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"redirect_uri must be an HTTP(S) URL, got: '{self.redirect_uri}'")
        if not parsed.hostname:
            raise ValueError(f"redirect_uri must include a hostname, got: '{self.redirect_uri}'")
        return self


_HMAC_ALGORITHMS = {"HS256", "HS384", "HS512"}


class BearerConfig(BaseModel):
    """JWT bearer token validation config."""

    algorithm: str = "HS256"
    secret_key: str = ""
    public_key: str = ""
    issuer: str = ""
    audience: str = ""

    @model_validator(mode="after")
    def _check_keys(self) -> BearerConfig:
        if self.algorithm in _HMAC_ALGORITHMS and not self.secret_key:
            env = os.environ.get("NINJASTACK_ENV", "").lower()
            if env in ("dev", "development", "test"):
                logger.warning(
                    "BearerConfig.secret_key is empty for HMAC algorithm '%s'. "
                    "Auto-generating a random key for %s mode.",
                    self.algorithm,
                    env,
                )
                self.secret_key = secrets.token_urlsafe(32)
                return self
            raise ValueError(
                f"BearerConfig.secret_key must not be empty when using "
                f"HMAC algorithm '{self.algorithm}'. Provide a secret key or "
                f"switch to an asymmetric algorithm (e.g. RS256)."
            )
        if self.algorithm not in _HMAC_ALGORITHMS and not self.public_key:
            raise ValueError(
                f"BearerConfig.public_key must not be empty when using asymmetric algorithm '{self.algorithm}'."
            )
        return self


class ApiKeyConfig(BaseModel):
    """API key strategy configuration.

    Key values support three formats:
    - ``sha256:<hex>`` — pre-hashed key (recommended for storage on disk)
    - ``$env:VAR_NAME`` — resolved from an environment variable at runtime
    - plain string  — legacy plaintext (hashed on the fly; avoid for production)
    """

    header_name: str = "X-API-Key"
    keys: dict[str, str] = Field(default_factory=dict)

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """Return the storage representation of a raw API key (``sha256:<hex>``)."""
        return f"{_HASH_PREFIX}{hashlib.sha256(raw_key.encode()).hexdigest()}"

    def resolve_key(self, stored_value: str) -> str | None:
        """Resolve a stored key value to a comparable hash.

        Returns the ``sha256:<hex>`` digest for the stored key, or *None*
        if the key cannot be resolved (e.g. missing env var).
        """
        if stored_value.startswith(_HASH_PREFIX):
            return stored_value
        if stored_value.startswith(_ENV_PREFIX):
            var_name = stored_value[len(_ENV_PREFIX) :]
            raw = os.environ.get(var_name)
            if raw is None:
                return None
            return self.hash_key(raw)
        # Legacy plaintext — hash it on the fly
        return self.hash_key(stored_value)


_INSECURE_TOKEN_SECRET = "change-me-in-production"


class IdentityConfig(BaseModel):
    """Built-in identity (registration/login) config."""

    enabled: bool = True
    hash_algorithm: str = "bcrypt"
    token_secret: str = _INSECURE_TOKEN_SECRET
    token_expiry_minutes: int = 60

    @model_validator(mode="after")
    def _check_token_secret(self) -> IdentityConfig:
        if self.token_secret != _INSECURE_TOKEN_SECRET:
            return self
        env = os.environ.get("NINJASTACK_ENV", "").lower()
        if env in ("dev", "development", "test"):
            logger.warning(
                "IdentityConfig.token_secret is using the insecure default. "
                "This is allowed in %s mode but MUST be changed for production.",
                env,
            )
            self.token_secret = secrets.token_urlsafe(32)
            return self
        raise ValueError(
            "IdentityConfig.token_secret still has the insecure default value "
            f"'{_INSECURE_TOKEN_SECRET}'. Set an explicit secret or set "
            "NINJASTACK_ENV=dev for local development."
        )


class AuthConfig(BaseModel):
    """Top-level auth configuration.

    Attributes:
        revocation_store: Optional token revocation store instance. When ``None``
            (the default), revocation checks are skipped entirely and the gateway
            operates in pure stateless JWT mode. Set to an implementation of
            :class:`~ninja_auth.revocation.TokenRevocationStore` (e.g.
            ``InMemoryRevocationStore``) to enable server-side token revocation
            and per-user session invalidation.
    """

    model_config = {"arbitrary_types_allowed": True}

    default_strategy: str = "bearer"
    public_paths: list[str] = Field(default_factory=lambda: ["/health", "/docs", "/openapi.json"])
    oauth2_providers: dict[str, OAuth2ProviderConfig] = Field(default_factory=dict)
    bearer: BearerConfig = Field(default_factory=BearerConfig)
    api_key: ApiKeyConfig = Field(default_factory=ApiKeyConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    rbac: RBACConfig = Field(default_factory=RBACConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    revocation_store: Any | None = Field(default=None, exclude=True)

    @classmethod
    def from_file(cls, path: str | Path = ".ninjastack/auth.json") -> AuthConfig:
        """Load config from a JSON file, falling back to defaults."""
        p = Path(path)
        if p.exists():
            data: dict[str, Any] = json.loads(p.read_text())
            return cls.model_validate(data)
        return cls()
