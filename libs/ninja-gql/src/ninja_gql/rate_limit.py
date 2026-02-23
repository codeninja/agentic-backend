"""Rate limiting middleware for the GraphQL endpoint.

Extends the sliding-window ``RateLimiter`` from ``ninja-auth`` to provide
per-IP (and optionally per-user) rate limiting on the ``/graphql`` endpoint,
with stricter limits configurable for mutations.
"""

from __future__ import annotations

import logging
from typing import Any

from ninja_auth.rate_limiter import RateLimitConfig, RateLimiter
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class GraphQLRateLimitConfig(BaseModel):
    """Rate limiting configuration for the GraphQL endpoint.

    Extends the base ``RateLimitConfig`` with separate query/mutation
    limits and optional per-user enforcement.
    """

    enabled: bool = Field(default=True, description="Enable rate limiting.")
    query_max_requests: int = Field(
        default=100,
        ge=1,
        description="Maximum requests per window for queries.",
    )
    mutation_max_requests: int = Field(
        default=50,
        ge=1,
        description="Maximum requests per window for mutations (stricter).",
    )
    window_seconds: int = Field(
        default=60,
        ge=1,
        description="Sliding window duration in seconds.",
    )
    per_user_enabled: bool = Field(
        default=False,
        description="Enable per-user rate limiting (requires auth context).",
    )
    per_user_max_requests: int = Field(
        default=200,
        ge=1,
        description="Maximum requests per window per authenticated user.",
    )
    graphql_path: str = Field(
        default="/graphql",
        description="Path to the GraphQL endpoint.",
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_mutation(body: dict[str, Any]) -> bool:
    """Check if the GraphQL request body contains a mutation."""
    query = body.get("query", "")
    if isinstance(query, str):
        return query.strip().lower().startswith("mutation")
    return False


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class GraphQLRateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces per-IP rate limiting on the GraphQL endpoint.

    Uses the sliding-window ``RateLimiter`` from ``ninja-auth`` with
    separate limits for queries and mutations.  When per-user limiting is
    enabled, authenticated users are tracked by their user ID in addition
    to IP-based limiting.
    """

    def __init__(self, app: Any, config: GraphQLRateLimitConfig | None = None) -> None:
        self._config = config or GraphQLRateLimitConfig()

        # Create separate rate limiters for queries and mutations
        self._query_limiter = RateLimiter(
            RateLimitConfig(
                enabled=self._config.enabled,
                max_attempts=self._config.query_max_requests,
                window_seconds=self._config.window_seconds,
            )
        )
        self._mutation_limiter = RateLimiter(
            RateLimitConfig(
                enabled=self._config.enabled,
                max_attempts=self._config.mutation_max_requests,
                window_seconds=self._config.window_seconds,
            )
        )
        self._user_limiter = RateLimiter(
            RateLimitConfig(
                enabled=self._config.per_user_enabled,
                max_attempts=self._config.per_user_max_requests,
                window_seconds=self._config.window_seconds,
            )
        )
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request, enforcing rate limits on the GraphQL endpoint."""
        if not self._config.enabled:
            return await call_next(request)

        # Only rate-limit the GraphQL endpoint
        if request.url.path != self._config.graphql_path:
            return await call_next(request)

        if request.method != "POST":
            return await call_next(request)

        ip = _client_ip(request)

        # Try to parse body to determine if mutation
        is_mutation = False
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                is_mutation = _is_mutation(body)
            except Exception:
                pass

        # Select limiter based on operation type
        limiter = self._mutation_limiter if is_mutation else self._query_limiter
        limit_key = f"ip:{ip}"

        if limiter.is_rate_limited(limit_key):
            op_type = "mutation" if is_mutation else "query"
            logger.warning(
                "GraphQL rate limit exceeded for %s on %s operation",
                ip,
                op_type,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "errors": [
                        {
                            "message": (f"Rate limit exceeded for {op_type} operations. Please try again later."),
                        }
                    ]
                },
            )

        # Per-user check (if enabled and user is authenticated)
        if self._config.per_user_enabled:
            user_context = getattr(request.state, "user", None)
            if user_context is not None:
                user_id = getattr(user_context, "user_id", None)
                if user_id and self._user_limiter.is_rate_limited(f"user:{user_id}"):
                    logger.warning(
                        "GraphQL per-user rate limit exceeded for user %s",
                        user_id,
                    )
                    return JSONResponse(
                        status_code=429,
                        content={
                            "errors": [
                                {
                                    "message": "Per-user rate limit exceeded. Please try again later.",
                                }
                            ]
                        },
                    )

        # Record the attempt and proceed
        limiter.record_attempt(limit_key, success=True)
        if self._config.per_user_enabled:
            user_context = getattr(request.state, "user", None)
            if user_context is not None:
                user_id = getattr(user_context, "user_id", None)
                if user_id:
                    self._user_limiter.record_attempt(f"user:{user_id}", success=True)

        return await call_next(request)
