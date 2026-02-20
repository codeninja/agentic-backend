"""ASGI/FastAPI middleware that intercepts requests and delegates to auth strategies."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ninja_auth.agent_context import set_user_context
from ninja_auth.config import AuthConfig
from ninja_auth.context import ANONYMOUS_USER, UserContext
from ninja_auth.strategies.apikey import ApiKeyStrategy
from ninja_auth.strategies.bearer import BearerStrategy

# Request state key for user context
USER_CONTEXT_KEY = "user_context"


class AuthGateway(BaseHTTPMiddleware):
    """Starlette middleware that authenticates requests and injects UserContext into request state."""

    def __init__(self, app: Any, config: AuthConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or AuthConfig()
        self._bearer = BearerStrategy(self.config.bearer)
        self._apikey = ApiKeyStrategy(self.config.api_key)

    def _is_public_path(self, path: str) -> bool:
        """Check if the request path matches any configured public path pattern."""
        return any(fnmatch(path, pattern) for pattern in self.config.public_paths)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Authenticate the request and inject user context."""
        # Allow public paths through without auth
        if self._is_public_path(request.url.path):
            request.state.user_context = ANONYMOUS_USER
            set_user_context(ANONYMOUS_USER)
            return await call_next(request)

        # Try each strategy in order
        user_ctx = await self._try_authenticate(request)

        if user_ctx is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

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
