"""Built-in identity strategy: user registration, login, password hashing."""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from ninja_auth.config import IdentityConfig
from ninja_auth.context import UserContext
from ninja_auth.user_store import InMemoryUserStore, UserStore

logger = logging.getLogger(__name__)


class IdentityStrategy:
    """Manages local user accounts with password hashing and JWT session tokens."""

    # Pre-computed dummy hash so missing-user lookups still run bcrypt,
    # preventing timing side-channel user enumeration.
    _DUMMY_HASH: str = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()

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

    def _validate_password(self, password: str) -> None:
        """Validate password against the configured policy.

        Raises:
            ValueError: If the password does not meet policy requirements.
        """
        policy = self.config.password_policy
        errors: list[str] = []

        if len(password) < policy.min_length:
            errors.append(f"at least {policy.min_length} characters")
        if policy.require_uppercase and not re.search(r"[A-Z]", password):
            errors.append("an uppercase letter")
        if policy.require_lowercase and not re.search(r"[a-z]", password):
            errors.append("a lowercase letter")
        if policy.require_digit and not re.search(r"\d", password):
            errors.append("a digit")
        if policy.require_special and not re.search(r"[^A-Za-z0-9]", password):
            errors.append("a special character")

        if errors:
            raise ValueError(f"Password does not meet policy: must contain {', '.join(errors)}")

    def register(self, email: str, password: str, roles: list[str] | None = None) -> UserContext:
        """Register a new user account."""
        self._validate_password(password)
        if self._store.exists(email):
            raise ValueError(f"User already exists: {email}")

        user_id = secrets.token_hex(16)
        assigned_roles = roles or []
        self._store.save(
            email,
            {
                "user_id": user_id,
                "email": email,
                "password_hash": self.hash_password(password),
                "roles": assigned_roles,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(
            "User registered: email=%s user_id=%s roles=%s",
            email,
            user_id,
            assigned_roles,
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
        # Always perform a hash comparison to prevent timing side-channel
        # user enumeration — missing users take the same time as wrong passwords.
        password_hash = user["password_hash"] if user else self._DUMMY_HASH
        password_valid = self.verify_password(password, password_hash)

        if not user:
            logger.warning(
                "Login failed: unknown email=%s",
                email,
                extra={"event": "login_failed", "reason": "unknown_email", "email": email},
            )
            return None
        if not password_valid:
            logger.warning(
                "Login failed: bad password for email=%s",
                email,
                extra={"event": "login_failed", "reason": "bad_password", "email": email},
            )
            return None

        user_id = user["user_id"]
        logger.info(
            "Login successful: email=%s user_id=%s",
            email,
            user_id,
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
