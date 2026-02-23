"""JWT bearer token validation strategy."""

from __future__ import annotations

import logging
import re
from typing import Any

import jwt
from starlette.requests import Request

from ninja_auth.config import BearerConfig
from ninja_auth.context import UserContext

logger = logging.getLogger(__name__)

# Claims that must be present in every JWT.
_REQUIRED_CLAIMS = ("sub", "exp")

# Lightweight email format check (RFC 5322 simplified).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Permission strings must follow the ``action:scope`` format.
_PERMISSION_RE = re.compile(r"^[a-zA-Z*]+:[a-zA-Z0-9.*_-]+$")

# Safe claim keys forwarded to metadata (excludes the full payload).
_SAFE_METADATA_CLAIMS = frozenset({"iss", "aud", "iat", "exp", "jti", "nbf"})


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

    @staticmethod
    def _validate_email(value: Any) -> str | None:
        """Return a validated email string, or ``None`` if invalid/absent."""
        if value is None:
            return None
        if not isinstance(value, str) or not _EMAIL_RE.match(value):
            logger.warning(
                "JWT 'email' claim has invalid format: %r",
                value,
                extra={"event": "claim_validation_failed", "claim": "email"},
            )
            return None
        return value

    @staticmethod
    def _validate_roles(value: Any) -> list[str]:
        """Return a validated list of role strings, dropping non-string entries."""
        if not isinstance(value, list):
            if value is not None:
                logger.warning(
                    "JWT 'roles' claim is not a list, ignoring",
                    extra={"event": "claim_validation_failed", "claim": "roles"},
                )
            return []
        valid: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                valid.append(item.strip())
            else:
                logger.warning(
                    "JWT 'roles' contains non-string or empty entry: %r, skipping",
                    item,
                    extra={"event": "claim_validation_failed", "claim": "roles"},
                )
        return valid

    @staticmethod
    def _validate_permissions(value: Any) -> list[str]:
        """Return a validated list of ``action:scope`` permission strings."""
        if not isinstance(value, list):
            if value is not None:
                logger.warning(
                    "JWT 'permissions' claim is not a list, ignoring",
                    extra={"event": "claim_validation_failed", "claim": "permissions"},
                )
            return []
        valid: list[str] = []
        for item in value:
            if isinstance(item, str) and _PERMISSION_RE.match(item):
                valid.append(item)
            else:
                logger.warning(
                    "JWT 'permissions' contains invalid entry: %r, skipping",
                    item,
                    extra={"event": "claim_validation_failed", "claim": "permissions"},
                )
        return valid

    @staticmethod
    def _safe_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        """Extract only safe, non-sensitive claims for metadata."""
        return {k: v for k, v in payload.items() if k in _SAFE_METADATA_CLAIMS}

    async def authenticate(self, request: Request) -> UserContext | None:
        """Extract and validate a JWT from the Authorization header.

        Returns ``None`` when no bearer token is present or the token is
        invalid, allowing the auth gateway to fall through to other
        strategies or treat the request as unauthenticated.
        """
        auth_header = request.headers.get("authorization", "")
        if not auth_header[:7].lower() == "bearer " or len(auth_header) <= 7:
            return None

        token = auth_header[7:]
        return self.validate_token(token)

    def validate_token(self, token: str) -> UserContext | None:
        """Decode and validate a JWT, returning ``UserContext`` on success.

        Validation includes:
        * Signature verification against the configured key/algorithm.
        * Optional ``iss`` (issuer) and ``aud`` (audience) checks when the
          corresponding config fields are set.
        * ``exp`` is required and validated by PyJWT.
        * Required claims (``sub``, ``exp``) must be present.
        * ``email`` is validated for format (RFC 5322 simplified).
        * ``roles`` must be a list of non-empty strings.
        * ``permissions`` must be a list of ``action:scope`` strings.
        * Raw JWT payload is **not** exposed in metadata — only safe
          standard claims (``iss``, ``aud``, ``iat``, ``exp``, ``jti``,
          ``nbf``) are forwarded.

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
                logger.warning(
                    "JWT 'sub' claim is empty or not a string",
                    extra={"event": "token_validation_failed", "reason": "invalid_sub"},
                )
                return None

            logger.debug(
                "Bearer token validated: user_id=%s",
                sub,
                extra={"event": "token_validated", "user_id": sub},
            )

            return UserContext(
                user_id=sub,
                email=self._validate_email(payload.get("email")),
                roles=self._validate_roles(payload.get("roles")),
                permissions=self._validate_permissions(payload.get("permissions")),
                provider="bearer",
                metadata=self._safe_metadata(payload),
            )
        except jwt.ExpiredSignatureError:
            # Attempt to extract identifiers from expired token for logging
            token_sub = None
            try:
                unverified = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
                token_sub = unverified.get("sub")
            except Exception:
                pass
            logger.warning(
                "Token validation failed: reason=expired sub=%s",
                token_sub,
                extra={"event": "token_validation_failed", "reason": "expired", "sub": token_sub},
            )
            return None
        except jwt.PyJWTError as exc:
            logger.error(
                "Token validation failed: reason=%s",
                type(exc).__name__,
                extra={"event": "token_validation_failed", "reason": type(exc).__name__},
            )
            return None
