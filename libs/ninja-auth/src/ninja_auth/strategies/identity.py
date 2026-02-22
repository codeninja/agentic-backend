"""Built-in identity strategy: user registration, login, password hashing."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from ninja_auth.config import IdentityConfig
from ninja_auth.context import UserContext
from ninja_auth.user_store import InMemoryUserStore, UserStore

logger = logging.getLogger(__name__)


class IdentityStrategy:
    """Manages local user accounts with password hashing and JWT session tokens."""

    def __init__(
        self,
        config: IdentityConfig,
        user_store: UserStore | None = None,
    ) -> None:
        self.config = config
        self._store: UserStore = user_store or InMemoryUserStore()

    def hash_password(self, password: str) -> str:
        """Hash a plaintext password using bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Verify a password against its bcrypt hash."""
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    def register(self, email: str, password: str, roles: list[str] | None = None) -> UserContext:
        """Register a new user account."""
        if self._store.exists(email):
            raise ValueError(f"User already exists: {email}")

        user_id = secrets.token_hex(16)
        assigned_roles = roles or []
        self._store.save(email, {
            "user_id": user_id,
            "email": email,
            "password_hash": self.hash_password(password),
            "roles": assigned_roles,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(
            "User registered: email=%s user_id=%s roles=%s",
            email, user_id, assigned_roles,
            extra={"event": "user_registered", "email": email, "user_id": user_id, "roles": assigned_roles},
        )

        return UserContext(
            user_id=user_id,
            email=email,
            roles=assigned_roles,
            provider="identity",
        )

    def login(self, email: str, password: str) -> UserContext | None:
        """Authenticate a user by email and password."""
        user = self._store.get(email)
        if not user:
            logger.warning(
                "Login failed: unknown email=%s",
                email,
                extra={"event": "login_failed", "reason": "unknown_email", "email": email},
            )
            return None
        if not self.verify_password(password, user["password_hash"]):
            logger.warning(
                "Login failed: bad password for email=%s",
                email,
                extra={"event": "login_failed", "reason": "bad_password", "email": email},
            )
            return None

        user_id = user["user_id"]
        logger.info(
            "Login successful: email=%s user_id=%s",
            email, user_id,
            extra={"event": "login_success", "email": email, "user_id": user_id},
        )

        return UserContext(
            user_id=user_id,
            email=user["email"],
            roles=user.get("roles", []),
            provider="identity",
        )

    def issue_token(self, user_ctx: UserContext) -> str:
        """Issue a JWT session token for an authenticated user."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_ctx.user_id,
            "email": user_ctx.email,
            "roles": user_ctx.roles,
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + timedelta(minutes=self.config.token_expiry_minutes),
        }
        token = jwt.encode(payload, self.config.token_secret, algorithm="HS256")
        logger.info(
            "Token issued: user_id=%s",
            user_ctx.user_id,
            extra={"event": "token_issued", "user_id": user_ctx.user_id},
        )
        return token

    def validate_token(self, token: str) -> UserContext | None:
        """Validate a session token and return user context."""
        try:
            payload = jwt.decode(token, self.config.token_secret, algorithms=["HS256"])
            return UserContext(
                user_id=payload["sub"],
                email=payload.get("email"),
                roles=payload.get("roles", []),
                provider="identity",
            )
        except jwt.PyJWTError:
            return None
