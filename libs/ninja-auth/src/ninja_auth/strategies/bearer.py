"""JWT bearer token validation strategy."""

from __future__ import annotations

import logging
from typing import Any

import jwt
from starlette.requests import Request

from ninja_auth.config import BearerConfig
from ninja_auth.context import UserContext

logger = logging.getLogger(__name__)

# Claims that must be present and non-empty in every JWT.
_REQUIRED_CLAIMS = ("sub",)


class BearerStrategy:
    """Validates JWT bearer tokens and extracts user context."""

    def __init__(self, config: BearerConfig) -> None:
        self.config = config

    def _get_signing_key(self) -> str:
        """Return the key used for token verification."""
        if self.config.public_key:
            return self.config.public_key
        return self.config.secret_key

    def _get_algorithms(self) -> list[str]:
        """Return the list of acceptable signing algorithms."""
        return [self.config.algorithm]

    async def authenticate(self, request: Request) -> UserContext | None:
        """Extract and validate a JWT from the Authorization header.

        Returns ``None`` when no bearer token is present or the token is
        invalid, allowing the auth gateway to fall through to other
        strategies or treat the request as unauthenticated.
        """
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        return self.validate_token(token)

    def validate_token(self, token: str) -> UserContext | None:
        """Decode and validate a JWT, returning ``UserContext`` on success.

        Validation includes:
        * Signature verification against the configured key/algorithm.
        * Optional ``iss`` (issuer) and ``aud`` (audience) checks when the
          corresponding config fields are set.
        * ``exp`` is validated by PyJWT automatically when present.
        * Required claims (``sub``) must be present and non-empty.

        Returns ``None`` for any invalid, expired, or incomplete token.
        """
        try:
            decode_opts: dict[str, Any] = {
                "algorithms": self._get_algorithms(),
                "options": {"require": list(_REQUIRED_CLAIMS)},
            }
            if self.config.issuer:
                decode_opts["issuer"] = self.config.issuer
            if self.config.audience:
                decode_opts["audience"] = self.config.audience

            payload = jwt.decode(
                token,
                self._get_signing_key(),
                **decode_opts,
            )

            sub = payload.get("sub")
            if not isinstance(sub, str) or not sub.strip():
                logger.warning("JWT 'sub' claim is empty or not a string")
                return None

            return UserContext(
                user_id=sub,
                email=payload.get("email"),
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", []),
                provider="bearer",
                metadata={"claims": payload},
            )
        except jwt.PyJWTError:
            return None
