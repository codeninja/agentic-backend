"""Built-in identity strategy: user registration, login, password hashing."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from ninja_auth.config import IdentityConfig
from ninja_auth.context import UserContext
from ninja_auth.user_store import InMemoryUserStore, UserStore


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
        self._store.save(email, {
            "user_id": user_id,
            "email": email,
            "password_hash": self.hash_password(password),
            "roles": roles or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        return UserContext(
            user_id=user_id,
            email=email,
            roles=roles or [],
            provider="identity",
        )

    def login(self, email: str, password: str) -> UserContext | None:
        """Authenticate a user by email and password."""
        user = self._store.get(email)
        if not user:
            return None
        if not self.verify_password(password, user["password_hash"]):
            return None

        return UserContext(
            user_id=user["user_id"],
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
            "iat": now,
            "exp": now + timedelta(minutes=self.config.token_expiry_minutes),
        }
        return jwt.encode(payload, self.config.token_secret, algorithm="HS256")

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
