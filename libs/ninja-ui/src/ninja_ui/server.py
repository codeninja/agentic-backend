"""Simple built-in server for serving generated UI files with security headers.

.. warning::

    This server is intended for **local development only**.  It is built on
    Python's :mod:`http.server` module which is explicitly documented as
    unsuitable for production use.  For production deployments, serve the
    generated UI files through a proper web server (e.g. Nginx) or a
    production-grade Python ASGI server such as uvicorn with Starlette's
    ``StaticFiles`` middleware.
"""

from __future__ import annotations

import http.server
import logging
import threading
from functools import partial
from pathlib import Path

logger = logging.getLogger(__name__)

# Content Security Policy that allows inline scripts (needed for generated
# single-file HTML pages) but blocks all other unsafe sources.  The
# connect-src directive allows fetch calls to 'self' for the GraphQL endpoint.
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# File extensions that may be served.  Requests for any other extension are
# rejected with a 403.  This prevents accidental exposure of source files,
# configuration, or other sensitive material that may live in the same tree.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".html",
        ".css",
        ".js",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".map",
    }
)


class _SecureHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that injects security headers and restricts file types.

    This handler extends :class:`~http.server.SimpleHTTPRequestHandler` with:

    * Standard security headers on every response.
    * An allow-list of servable file extensions (see :data:`ALLOWED_EXTENSIONS`).
    * Directory traversal protection via path canonicalisation.
    * ``Cache-Control`` headers appropriate for development use.
    """

    def end_headers(self) -> None:
        """Add security headers before finalising the response."""
        self.send_header("Content-Security-Policy", DEFAULT_CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    # Silence per-request log lines from the stdlib handler.
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Route access log messages through the standard logging module."""
        logger.debug(format, *args)

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests with path and extension validation."""
        if not self._is_request_allowed():
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        """Handle HEAD requests with path and extension validation."""
        if not self._is_request_allowed():
            return
        super().do_HEAD()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_request_allowed(self) -> bool:
        """Validate the request path against traversal and extension rules.

        Returns ``True`` if the request may proceed, ``False`` if a 403 has
        already been sent.
        """
        # Translate the URL path to a filesystem path so we can validate it.
        # ``translate_path`` resolves ``..`` segments and maps the URL to the
        # configured directory.
        fs_path = Path(self.translate_path(self.path))

        # Directory listing / index resolution — allow it (the parent class
        # will serve ``index.html`` if present or return 404).
        if fs_path.is_dir():
            return True

        # Ensure the resolved path lives under the configured root directory.
        # ``translate_path`` already resolves ``..`` but an explicit check
        # prevents any edge-case escapes.
        root = Path(self.directory).resolve()  # type: ignore[attr-defined]
        try:
            fs_path.resolve().relative_to(root)
        except ValueError:
            self.send_error(403, "Forbidden")
            return False

        # Reject files whose extension is not in the allow-list.
        if fs_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            self.send_error(403, "Forbidden")
            return False

        return True


class UIServer:
    """Serves generated UI files via a simple HTTP server with security headers.

    .. warning::

        This server is for **local development only**.  Do not expose it to
        untrusted networks.  For production deployments, use a dedicated web
        server or ASGI framework.
    """

    def __init__(self, root_dir: Path, host: str = "127.0.0.1", port: int = 8080) -> None:
        self.root_dir = root_dir
        self.host = host
        self.port = port
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self, *, background: bool = False) -> None:
        """Start serving the UI directory.

        Args:
            background: If True, run in a background thread.
        """
        if self.host != "127.0.0.1":
            logger.warning(
                "UIServer is binding to %s — this server is intended for "
                "local development only. Do not expose to untrusted networks.",
                self.host,
            )

        class Handler(_SecureHandler):
            pass

        handler = partial(Handler, directory=str(self.root_dir))
        self._server = http.server.HTTPServer((self.host, self.port), handler)

        if background:
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
        else:
            self._server.serve_forever()

    def stop(self) -> None:
        """Stop the server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
            self._thread = None

    @property
    def url(self) -> str:
        """Return the base URL of the server."""
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._server is not None
