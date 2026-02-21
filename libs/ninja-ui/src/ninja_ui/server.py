"""Simple built-in server for serving generated UI files with security headers."""

from __future__ import annotations

import http.server
import threading
from functools import partial
from pathlib import Path

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


class _SecureHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that injects security headers into every response."""

    def end_headers(self) -> None:
        """Add security headers before finalising the response."""
        self.send_header("Content-Security-Policy", DEFAULT_CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()


class UIServer:
    """Serves generated UI files via a simple HTTP server with security headers."""

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
