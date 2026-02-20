"""Simple built-in server for serving generated UI files."""

from __future__ import annotations

import http.server
import threading
from functools import partial
from pathlib import Path


class UIServer:
    """Serves generated UI files via a simple HTTP server."""

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
        handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(self.root_dir))
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
