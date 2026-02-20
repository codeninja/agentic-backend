"""JWT bearer token validation strategy."""

from __future__ import annotations

from typing import Any

import jwt
from starlette.requests import Request

from ninja_auth.config import BearerConfig
from ninja_auth.context import UserContext


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
        return [self.config.algorithm]

    async def authenticate(self, request: Request) -> UserContext | None:
        """Extract and validate a JWT from the Authorization header."""
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        return self.validate_token(token)

    def validate_token(self, token: str) -> UserContext | None:
        """Decode and validate a JWT, returning UserContext on success."""
        try:
            decode_opts: dict[str, Any] = {
                "algorithms": self._get_algorithms(),
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

            return UserContext(
                user_id=payload.get("sub", ""),
                email=payload.get("email"),
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", []),
                provider="bearer",
                metadata={"claims": payload},
            )
        except jwt.PyJWTError:
            return None
