"""ASGI/FastAPI middleware that intercepts requests and delegates to auth strategies."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ninja_auth.agent_context import set_rbac_policy, set_user_context
from ninja_auth.config import AuthConfig
from ninja_auth.context import ANONYMOUS_USER, UserContext
from ninja_auth.errors import AuthenticationError
from ninja_auth.rate_limiter import InMemoryRateLimiter, RateLimiterProtocol
from ninja_auth.rbac import RBACPolicy
from ninja_auth.strategies.apikey import ApiKeyStrategy
from ninja_auth.strategies.bearer import BearerStrategy

logger = logging.getLogger(__name__)

# Request state key for user context
USER_CONTEXT_KEY = "user_context"


def _client_ip(request: Request) -> str:
    """Extract the client IP from a request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class AuthGateway(BaseHTTPMiddleware):
    """Starlette middleware that authenticates requests and injects UserContext into request state."""

    def __init__(
        self,
        app: Any,
        config: AuthConfig | None = None,
        rate_limiter: RateLimiterProtocol | None = None,
    ) -> None:
        super().__init__(app)
        self.config = config or AuthConfig()
        self._bearer = BearerStrategy(self.config.bearer)
        self._apikey = ApiKeyStrategy(self.config.api_key)
        self._rbac = RBACPolicy(self.config.rbac)
        self._rate_limiter: RateLimiterProtocol = rate_limiter or InMemoryRateLimiter(self.config.rate_limit)
        self._revocation_store = self.config.revocation_store

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize a URL path for comparison.

        Strips query strings and fragments, removes trailing slashes (preserving
        the root ``/``), and collapses consecutive slashes.
        """
        # Strip query string and fragment
        path = urlparse(path).path
        # Collapse consecutive slashes (e.g. "//health" -> "/health")
        while "//" in path:
            path = path.replace("//", "/")
        # Strip trailing slash, but keep root "/"
        if path != "/":
            path = path.rstrip("/")
        return path

    def _is_public_path(self, path: str) -> bool:
        """Check if the request path matches any configured public path.

        Matching uses **exact equality** after normalizing both the request path
        and each configured public path (trailing-slash removal, query-string
        stripping).  Wildcard / glob characters are **not** interpreted — this
        avoids accidental over-matching that could lead to auth bypass.
        """
        normalized = self._normalize_path(path)
        return any(
            normalized == self._normalize_path(pattern)
            for pattern in self.config.public_paths
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Authenticate the request and inject user context."""
        # Propagate the configured RBAC policy so agent tools use custom roles
        set_rbac_policy(self._rbac)

        # Allow public paths through without auth
        if self._is_public_path(request.url.path):
            request.state.user_context = ANONYMOUS_USER
            set_user_context(ANONYMOUS_USER)
            return await call_next(request)

        client_ip = _client_ip(request)

        # Check rate limit before attempting authentication
        if self._rate_limiter.is_rate_limited(client_ip):
            logger.warning(
                "Rate limited: ip=%s path=%s",
                client_ip,
                request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many authentication attempts. Please try again later."},
            )

        # Try each strategy in order
        user_ctx = await self._try_authenticate(request)

        if user_ctx is not None:
            logger.info(
                "Authentication successful: user_id=%s provider=%s ip=%s path=%s",
                user_ctx.user_id,
                user_ctx.provider,
                client_ip,
                request.url.path,
                extra={
                    "event": "auth_success",
                    "user_id": user_ctx.user_id,
                    "provider": user_ctx.provider,
                    "ip": client_ip,
                    "path": str(request.url.path),
                },
            )

        if user_ctx is None:
            self._rate_limiter.record_attempt(client_ip, success=False)
            logger.warning(
                "Authentication failed: ip=%s path=%s method=%s",
                client_ip,
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        self._rate_limiter.record_attempt(client_ip, success=True)

        # Check token revocation if a revocation store is configured
        if self._revocation_store and user_ctx:
            try:
                await self._check_revocation(user_ctx)
            except AuthenticationError as exc:
                logger.warning(
                    "Token revoked: ip=%s path=%s user=%s reason=%s",
                    client_ip,
                    request.url.path,
                    user_ctx.user_id,
                    str(exc),
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": str(exc)},
                )

        # Enrich user context with RBAC-resolved permissions
        user_ctx = self._enrich_permissions(user_ctx)

        # Inject user context into request state and contextvar for agent tools
        request.state.user_context = user_ctx
        set_user_context(user_ctx)
        return await call_next(request)

    async def _try_authenticate(self, request: Request) -> UserContext | None:
        """Try strategies in priority order: Bearer, API key."""
        # Bearer JWT
        ctx = await self._bearer.authenticate(request)
        if ctx is not None:
            return ctx

        # API key
        ctx = await self._apikey.authenticate(request)
        if ctx is not None:
            return ctx

        return None

    async def _check_revocation(self, ctx: UserContext) -> None:
        """Check if the authenticated token has been revoked.

        Raises:
            AuthenticationError: If the token's ``jti`` has been individually
                revoked, or if the token was issued before the user's
                revocation cutoff timestamp.
        """
        claims = ctx.metadata.get("claims") or {}

        # Per-token revocation check
        jti = claims.get("jti")
        if jti and await self._revocation_store.is_token_revoked(jti):
            raise AuthenticationError("Token has been revoked")

        # Per-user revocation check (all tokens issued before a cutoff)
        iat_raw = claims.get("iat")
        if iat_raw and ctx.user_id:
            revoked_before = await self._revocation_store.get_user_revoked_before(ctx.user_id)
            if revoked_before:
                iat = datetime.fromtimestamp(iat_raw, tz=timezone.utc)
                if iat < revoked_before:
                    raise AuthenticationError("Session invalidated")

    def _enrich_permissions(self, ctx: UserContext) -> UserContext:
        """Resolve role-based permissions and merge them into the user context."""
        if not self._rbac.enabled or not ctx.roles:
            return ctx
        role_perms = self._rbac.permissions_for_roles(ctx.roles)
        if not role_perms:
            return ctx
        # Merge role-resolved permissions with any already present
        merged = list(ctx.permissions)
        seen = set(merged)
        for p in role_perms:
            if p not in seen:
                seen.add(p)
                merged.append(p)
        return ctx.model_copy(update={"permissions": merged})


def get_user_context(request: Request) -> UserContext:
    """FastAPI dependency to extract the authenticated user context from request state.

    Usage:
        @app.get("/me")
        async def me(user: UserContext = Depends(get_user_context)):
            return user
    """
    ctx: UserContext | None = getattr(request.state, USER_CONTEXT_KEY, None)
    if ctx is None:
        return ANONYMOUS_USER
    return ctx
