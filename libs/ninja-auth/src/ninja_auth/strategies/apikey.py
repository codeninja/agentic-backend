"""API key validation strategy for service-to-service auth."""

from __future__ import annotations

import hashlib
import hmac

from starlette.requests import Request

from ninja_auth.config import ApiKeyConfig
from ninja_auth.context import UserContext


class ApiKeyStrategy:
    """Validates API keys from a configured header against known keys."""

    def __init__(self, config: ApiKeyConfig) -> None:
        self.config = config

    async def authenticate(self, request: Request) -> UserContext | None:
        """Check the request header for a valid API key."""
        api_key = request.headers.get(self.config.header_name.lower(), "")
        if not api_key:
            # Also check query param as fallback
            api_key = request.query_params.get("api_key", "")
        if not api_key:
            return None

        return self.validate_key(api_key)

    def validate_key(self, api_key: str) -> UserContext | None:
        """Validate an API key against configured keys using constant-time comparison."""
        for name, known_key in self.config.keys.items():
            if hmac.compare_digest(
                hashlib.sha256(api_key.encode()).hexdigest(),
                hashlib.sha256(known_key.encode()).hexdigest(),
            ):
                return UserContext(
                    user_id=f"apikey:{name}",
                    roles=["service"],
                    provider="apikey",
                    metadata={"key_name": name},
                )
        return None
