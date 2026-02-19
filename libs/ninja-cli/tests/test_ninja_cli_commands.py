"""Tests for the ninjastack CLI commands."""

import json

from ninja_cli.cli import app
from typer.testing import CliRunner

runner = CliRunner()


class TestInitCommand:
    def test_init_creates_ninjastack_dir(self, tmp_path):
        result = runner.invoke(app, ["init", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Initialized" in result.output
        assert (tmp_path / ".ninjastack" / "schema.json").is_file()

    def test_init_custom_name(self, tmp_path):
        result = runner.invoke(app, ["init", "--name", "my-app", "--root", str(tmp_path)])
        assert result.exit_code == 0
        data = json.loads((tmp_path / ".ninjastack" / "schema.json").read_text())
        assert data["project_name"] == "my-app"

    def test_init_idempotent(self, tmp_path):
        runner.invoke(app, ["init", "--root", str(tmp_path)])
        result = runner.invoke(app, ["init", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestStubCommands:
    def test_sync_stub(self):
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0
        assert "Not yet implemented" in result.output

    def test_serve_stub(self):
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        assert "Not yet implemented" in result.output

    def test_deploy_stub(self):
        result = runner.invoke(app, ["deploy"])
        assert result.exit_code == 0
        assert "Not yet implemented" in result.output


class TestCreateCommands:
    def test_create_lib_missing_script(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "lib", "ninja-foo"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_create_app_missing_script(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "app", "ninja-foo"])
        assert result.exit_code == 1
        assert "not found" in result.output
