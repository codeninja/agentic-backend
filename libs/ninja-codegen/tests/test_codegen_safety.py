"""Tests for codegen safety — Jinja2 sandboxing, identifier filter, path traversal."""

from pathlib import Path

import pytest
from jinja2.sandbox import SandboxedEnvironment
from ninja_codegen.generators.base import (
    _safe_identifier,
    get_template_env,
    validate_output_path,
)


class TestSafeIdentifierFilter:
    def test_valid_identifier(self) -> None:
        assert _safe_identifier("Order") == "Order"

    def test_valid_snake_case(self) -> None:
        assert _safe_identifier("audit_log") == "audit_log"

    def test_rejects_special_chars(self) -> None:
        with pytest.raises(ValueError, match="Unsafe identifier"):
            _safe_identifier("Order;DROP TABLE")

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValueError, match="Unsafe identifier"):
            _safe_identifier("Order Management")

    def test_rejects_starts_with_number(self) -> None:
        with pytest.raises(ValueError, match="Unsafe identifier"):
            _safe_identifier("1Entity")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValueError, match="Unsafe identifier"):
            _safe_identifier("A" * 65)

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(ValueError, match="Unsafe identifier"):
            _safe_identifier("../../etc/passwd")


class TestSandboxedEnvironment:
    def test_env_is_sandboxed(self) -> None:
        env = get_template_env()
        assert isinstance(env, SandboxedEnvironment)

    def test_env_has_safe_identifier_filter(self) -> None:
        env = get_template_env()
        assert "safe_identifier" in env.filters

    def test_env_has_repr_filter(self) -> None:
        env = get_template_env()
        assert "repr" in env.filters


class TestValidateOutputPath:
    def test_valid_path(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        file_path = output_dir / "entity.py"
        result = validate_output_path(output_dir, file_path)
        assert str(result).startswith(str(output_dir.resolve()))

    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        file_path = output_dir / ".." / ".." / "etc" / "passwd"
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_output_path(output_dir, file_path)

    def test_rejects_absolute_escape(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        file_path = Path("/etc/passwd")
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_output_path(output_dir, file_path)

    def test_allows_subdirectory(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        sub_dir = output_dir / "models"
        sub_dir.mkdir(parents=True)
        file_path = sub_dir / "entity.py"
        result = validate_output_path(output_dir, file_path)
        assert str(result).startswith(str(output_dir.resolve()))
