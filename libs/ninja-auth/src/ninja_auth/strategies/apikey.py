"""API key validation strategy for service-to-service auth."""

from __future__ import annotations

import hmac
import logging

from starlette.requests import Request

from ninja_auth.config import ApiKeyConfig
from ninja_auth.context import UserContext

logger = logging.getLogger(__name__)


class ApiKeyStrategy:
    """Validates API keys from a configured header against known keys."""

    def __init__(self, config: ApiKeyConfig) -> None:
        self.config = config

    async def authenticate(self, request: Request) -> UserContext | None:
        """Check the request header for a valid API key.

        Only accepts API keys from the configured header. Query parameter
        delivery is not supported to prevent credential leakage in server logs,
        proxy logs, and browser history.
        """
        api_key = request.headers.get(self.config.header_name.lower(), "")
        if not api_key:
            return None

        return self.validate_key(api_key)

    def validate_key(self, api_key: str) -> UserContext | None:
        """Validate an API key against configured keys using constant-time comparison.

        The incoming *api_key* is hashed and compared against the stored value
        which is already in ``sha256:<hex>`` form (pre-hashed, env-var resolved,
        or legacy plaintext hashed on the fly via ``ApiKeyConfig.resolve_key``).
        """
        input_hash = self.config.hash_key(api_key)
        for name, stored_value in self.config.keys.items():
            expected_hash = self.config.resolve_key(stored_value)
            if expected_hash is None:
                continue
            if hmac.compare_digest(input_hash, expected_hash):
                logger.info(
                    "API key validated: key_name=%s user_id=apikey:%s",
                    name,
                    name,
                    extra={"event": "apikey_validated", "key_name": name, "user_id": f"apikey:{name}"},
                )
                return UserContext(
                    user_id=f"apikey:{name}",
                    roles=["service"],
                    provider="apikey",
                    metadata={"key_name": name},
                )
        key_prefix = api_key[:8] if len(api_key) >= 8 else api_key[:4] + "..."
        logger.warning(
            "Invalid API key: key_prefix=%s",
            key_prefix,
            extra={"event": "apikey_invalid", "key_prefix": key_prefix},
        )
        return None
