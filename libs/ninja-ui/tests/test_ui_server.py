"""Tests for the built-in UI server."""

from __future__ import annotations

import time
import urllib.request

import pytest
from ninja_ui.server import UIServer


@pytest.fixture()
def ui_root(tmp_path):
    """Create a minimal UI directory with an index page."""
    index = tmp_path / "index.html"
    index.write_text("<!DOCTYPE html><html><body>Hello</body></html>")
    return tmp_path


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
