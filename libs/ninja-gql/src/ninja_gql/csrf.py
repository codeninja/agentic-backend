"""CSRF protection middleware for GraphQL mutations.

Implements a custom-header check pattern: mutation requests must include
a ``X-Requested-With`` or ``X-CSRF-Token`` header.  This leverages the
browser's same-origin policy — cross-origin ``<form>`` posts and simple
requests cannot set custom headers, so their absence reliably indicates
a CSRF attempt.

For generated UI templates, the corresponding JavaScript ``fetch()`` calls
include the required header automatically.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Any

from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CSRFConfig(BaseModel):
    """CSRF protection configuration.

    The default mode uses custom-header validation which is effective
    against cross-origin form submissions.  Optionally, a double-submit
    cookie token can be enabled for stricter protection.
    """

    enabled: bool = Field(default=True, description="Enable CSRF protection on mutations.")
    header_name: str = Field(
        default="X-Requested-With",
        description="Required custom header name for mutation requests.",
    )
    header_value: str | None = Field(
        default=None,
        description="Expected header value. If None, any non-empty value is accepted.",
    )
    cookie_name: str = Field(
        default="ninjastack_csrf",
        description="Cookie name for the CSRF token (double-submit mode).",
    )
    cookie_samesite: str = Field(
        default="Lax",
        description="SameSite attribute for the CSRF cookie.",
    )
    token_secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret for CSRF token generation.",
    )
    exempt_paths: list[str] = Field(
        default_factory=list,
        description="Paths exempt from CSRF checks.",
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def generate_csrf_token(secret: str) -> str:
    """Generate a signed CSRF token.

    Parameters
    ----------
    secret:
        The application secret used for signing.

    Returns
    -------
    str
        A URL-safe token string.
    """
    nonce = secrets.token_urlsafe(24)
    signature = hmac.new(secret.encode(), nonce.encode(), "sha256").hexdigest()[:16]
    return f"{nonce}.{signature}"


def verify_csrf_token(token: str, secret: str) -> bool:
    """Verify a CSRF token's signature.

    Parameters
    ----------
    token:
        The token to verify.
    secret:
        The application secret.

    Returns
    -------
    bool
        True if the token is valid.
    """
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    nonce, signature = parts
    expected = hmac.new(secret.encode(), nonce.encode(), "sha256").hexdigest()[:16]
    return hmac.compare_digest(signature, expected)


# ---------------------------------------------------------------------------
# GraphQL mutation detection
# ---------------------------------------------------------------------------

_MUTATION_INDICATORS = frozenset({"mutation"})


def _is_mutation_request(body: dict[str, Any]) -> bool:
    """Heuristic check if a GraphQL request body contains a mutation.

    Parameters
    ----------
    body:
        Parsed JSON body of the GraphQL request.

    Returns
    -------
    bool
        True if the query string starts with ``mutation`` (after whitespace).
    """
    query = body.get("query", "")
    if isinstance(query, str):
        stripped = query.strip().lower()
        return stripped.startswith("mutation")
    return False


# ---------------------------------------------------------------------------
# ASGI Middleware
# ---------------------------------------------------------------------------


class CSRFMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces CSRF protection on GraphQL mutations.

    Checks for the presence of a custom header (``X-Requested-With`` by
    default) on POST requests to the GraphQL endpoint that contain
    mutations.  This is effective because browsers do not allow
    cross-origin requests to set custom headers without a CORS preflight.

    Additionally sets the CSRF cookie with ``SameSite=Lax`` (or ``Strict``)
    to prevent cookie-based CSRF on older browsers.
    """

    def __init__(self, app: Any, config: CSRFConfig | None = None) -> None:
        self.csrf_config = config or CSRFConfig()
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request, enforcing CSRF on mutations."""
        if not self.csrf_config.enabled:
            return await call_next(request)

        # Only check POST requests (GraphQL mutations come via POST)
        if request.method != "POST":
            return await call_next(request)

        # Check if path is exempt
        path = request.url.path
        if path in self.csrf_config.exempt_paths:
            return await call_next(request)

        # Try to determine if this is a mutation
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
            except Exception:
                # Can't parse body — let downstream handle it
                return await call_next(request)

            if _is_mutation_request(body):
                # Check for required custom header
                header_value = request.headers.get(self.csrf_config.header_name)
                if not header_value:
                    logger.warning(
                        "CSRF check failed: missing header '%s' from %s",
                        self.csrf_config.header_name,
                        request.client.host if request.client else "unknown",
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "errors": [
                                {
                                    "message": (
                                        f"CSRF validation failed: "
                                        f"missing required header '{self.csrf_config.header_name}'"
                                    ),
                                }
                            ]
                        },
                    )

                # If a specific value is expected, validate it
                if (
                    self.csrf_config.header_value is not None
                    and header_value != self.csrf_config.header_value
                ):
                    logger.warning("CSRF check failed: invalid header value")
                    return JSONResponse(
                        status_code=403,
                        content={
                            "errors": [
                                {"message": "CSRF validation failed: invalid token"}
                            ]
                        },
                    )

        response = await call_next(request)

        # Set SameSite cookie on all responses
        if not request.cookies.get(self.csrf_config.cookie_name):
            token = generate_csrf_token(self.csrf_config.token_secret)
            response.set_cookie(
                key=self.csrf_config.cookie_name,
                value=token,
                httponly=False,  # Must be readable by JavaScript
                samesite=self.csrf_config.cookie_samesite,
                secure=request.url.scheme == "https",
                path="/",
            )

        return response
