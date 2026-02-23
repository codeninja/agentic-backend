"""Tests for the built-in UI server."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

import pytest
from ninja_ui.server import ALLOWED_EXTENSIONS, UIServer


@pytest.fixture()
def ui_root(tmp_path):
    """Create a minimal UI directory with an index page."""
    index = tmp_path / "index.html"
    index.write_text("<!DOCTYPE html><html><body>Hello</body></html>")
    return tmp_path


def _get(url: str) -> urllib.request.Request:
    """Build a simple GET request."""
    return urllib.request.Request(url, method="GET")


class TestUIServer:
    """Tests for UIServer."""

    def test_init(self, ui_root):
        server = UIServer(ui_root)
        assert server.root_dir == ui_root
        assert server.host == "127.0.0.1"
        assert server.port == 8080

    def test_custom_host_port(self, ui_root):
        server = UIServer(ui_root, host="0.0.0.0", port=9090)
        assert server.host == "0.0.0.0"
        assert server.port == 9090

    def test_url_property(self, ui_root):
        server = UIServer(ui_root, port=3000)
        assert server.url == "http://127.0.0.1:3000"

    def test_is_running_initially_false(self, ui_root):
        server = UIServer(ui_root)
        assert server.is_running is False

    def test_start_background_and_stop(self, ui_root):
        server = UIServer(ui_root, port=18765)
        server.start(background=True)
        try:
            assert server.is_running is True
            time.sleep(0.3)
            resp = urllib.request.urlopen("http://127.0.0.1:18765/index.html")
            assert resp.status == 200
            body = resp.read().decode()
            assert "Hello" in body
        finally:
            server.stop()
        assert server.is_running is False

    def test_stop_idempotent(self, ui_root):
        server = UIServer(ui_root)
        server.stop()
        server.stop()
        assert server.is_running is False

    def test_serves_generated_ui(self, ui_root, sample_asd, tmp_path):
        from ninja_ui.generator import UIGenerator

        gen = UIGenerator(sample_asd)
        gen.generate(tmp_path)
        server = UIServer(tmp_path, port=18766)
        server.start(background=True)
        try:
            time.sleep(0.3)
            resp = urllib.request.urlopen("http://127.0.0.1:18766/crud/index.html")
            assert resp.status == 200
            body = resp.read().decode()
            assert "test-shop" in body
        finally:
            server.stop()


class TestSecureHandlerHeaders:
    """Verify the secure handler sends all required headers."""

    @pytest.fixture(autouse=True)
    def _server(self, tmp_path):
        """Start a server for each test in this class."""
        index = tmp_path / "index.html"
        index.write_text("<!DOCTYPE html><html><body>OK</body></html>")
        self.server = UIServer(tmp_path, port=18870)
        self.server.start(background=True)
        time.sleep(0.3)
        yield
        self.server.stop()

    def _fetch(self, path: str = "/index.html") -> urllib.request.http.client.HTTPResponse:
        return urllib.request.urlopen(f"http://127.0.0.1:18870{path}")

    def test_cache_control_no_store(self):
        """Server must send Cache-Control: no-store for development."""
        resp = self._fetch()
        cc = resp.headers.get("Cache-Control", "")
        assert "no-store" in cc

    def test_permissions_policy(self):
        resp = self._fetch()
        pp = resp.headers.get("Permissions-Policy", "")
        assert "camera=()" in pp
        assert "microphone=()" in pp
        assert "geolocation=()" in pp


class TestFileTypeRestriction:
    """Verify that only allowed file extensions are served."""

    @pytest.fixture(autouse=True)
    def _server(self, tmp_path):
        """Create files with various extensions and start a server."""
        (tmp_path / "index.html").write_text("<html>OK</html>")
        (tmp_path / "style.css").write_text("body{}")
        (tmp_path / "app.js").write_text("console.log('ok')")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "logo.png").write_bytes(b"\x89PNG")
        (tmp_path / "logo.svg").write_text("<svg/>")
        (tmp_path / "font.woff2").write_bytes(b"\x00")
        # Disallowed file types
        (tmp_path / "secret.py").write_text("password='hunter2'")
        (tmp_path / "config.yaml").write_text("key: value")
        (tmp_path / "data.sql").write_text("SELECT * FROM users")
        (tmp_path / ".env").write_text("API_KEY=secret")
        (tmp_path / "notes.txt").write_text("internal notes")
        (tmp_path / "backup.tar.gz").write_bytes(b"\x1f\x8b")
        self.server = UIServer(tmp_path, port=18871)
        self.server.start(background=True)
        time.sleep(0.3)
        yield
        self.server.stop()

    def _fetch(self, path: str) -> int:
        """Return the HTTP status code for a GET request."""
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:18871{path}")
            return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code

    @pytest.mark.parametrize(
        "path",
        ["/index.html", "/style.css", "/app.js", "/data.json", "/logo.png", "/logo.svg", "/font.woff2"],
    )
    def test_allowed_extensions_served(self, path):
        assert self._fetch(path) == 200

    @pytest.mark.parametrize(
        "path",
        ["/secret.py", "/config.yaml", "/data.sql", "/.env", "/notes.txt", "/backup.tar.gz"],
    )
    def test_disallowed_extensions_rejected(self, path):
        assert self._fetch(path) == 403

    def test_allowed_extensions_constant_is_frozen(self):
        """ALLOWED_EXTENSIONS should be immutable."""
        assert isinstance(ALLOWED_EXTENSIONS, frozenset)

    def test_common_web_extensions_in_allowlist(self):
        """Verify all expected web-asset extensions are in the allow-list."""
        for ext in (".html", ".css", ".js", ".json", ".png", ".jpg", ".svg", ".ico"):
            assert ext in ALLOWED_EXTENSIONS, f"{ext} missing from ALLOWED_EXTENSIONS"


class TestDirectoryTraversalProtection:
    """Verify that path traversal attacks are blocked."""

    @pytest.fixture(autouse=True)
    def _server(self, tmp_path):
        """Set up a server with a root dir and a sensitive file outside it."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        (ui_dir / "index.html").write_text("<html>OK</html>")
        # Sensitive file outside the root
        (tmp_path / "secret.html").write_text("TOP SECRET")
        self.server = UIServer(ui_dir, port=18872)
        self.server.start(background=True)
        time.sleep(0.3)
        yield
        self.server.stop()

    def _fetch(self, path: str) -> int:
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:18872{path}")
            return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_normal_file_served(self):
        assert self._fetch("/index.html") == 200

    def test_traversal_with_dot_dot_blocked(self):
        """Attempt to read ../secret.html should fail."""
        status = self._fetch("/../secret.html")
        # Should be either 403 (blocked) or 404 (not found) — never 200
        assert status in (403, 404)

    def test_encoded_traversal_blocked(self):
        """Attempt to use %2e%2e for traversal should fail."""
        status = self._fetch("/%2e%2e/secret.html")
        assert status in (403, 404)


class TestNonLocalhostWarning:
    """Verify that binding to non-localhost emits a warning."""

    def test_warning_on_non_localhost_bind(self, tmp_path, caplog):
        """Starting on 0.0.0.0 should log a warning."""
        import logging

        (tmp_path / "index.html").write_text("<html>OK</html>")
        server = UIServer(tmp_path, host="0.0.0.0", port=18873)
        with caplog.at_level(logging.WARNING, logger="ninja_ui.server"):
            server.start(background=True)
            time.sleep(0.2)
        server.stop()
        assert any("local development only" in rec.message for rec in caplog.records)
