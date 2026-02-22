"""Tests for the ninjastack CLI commands."""

import json

import pytest
import typer
from ninja_cli.cli import _validate_name, app
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


class TestValidateName:
    """Tests for _validate_name input sanitization (issue #54)."""

    @pytest.mark.parametrize(
        "name",
        [
            "ninja-foo",
            "a",
            "my-lib-2",
            "x123",
            "abc-def-ghi",
        ],
    )
    def test_valid_names_accepted(self, name):
        assert _validate_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",  # empty
            "Uppercase",  # uppercase letters
            "123start",  # starts with digit
            "-leading-hyphen",  # starts with hyphen
            "has spaces",  # spaces
            "semi;colon",  # shell metacharacter
            "pipe|char",  # shell metacharacter
            "back`tick",  # shell metacharacter
            "$(cmd)",  # command substitution
            "../traversal",  # path traversal
            "foo\nbar",  # newline injection
            "a" * 65,  # exceeds max length
            "ninja_underscore",  # underscores not allowed
            "has.dot",  # dots not allowed
        ],
    )
    def test_invalid_names_rejected(self, name):
        with pytest.raises(typer.BadParameter):
            _validate_name(name)

    def test_max_length_boundary(self):
        assert _validate_name("a" * 64) == "a" * 64
        with pytest.raises(typer.BadParameter):
            _validate_name("a" * 65)

    def test_create_lib_rejects_invalid_name(self, tmp_path, monkeypatch):
        """Integration test: invalid names are rejected before subprocess call."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "lib", "../etc/passwd"])
        assert result.exit_code != 0
        assert "Invalid name" in result.output

    def test_create_app_rejects_invalid_name(self, tmp_path, monkeypatch):
        """Integration test: invalid names are rejected before subprocess call."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "app", "$(rm -rf /)"])
        assert result.exit_code != 0
        assert "Invalid name" in result.output


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
