"""Tests for codegen safety — Jinja2 sandboxing, identifier filter, path traversal."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jinja2.sandbox import SandboxedEnvironment
from ninja_codegen.generators.base import (
    _safe_identifier,
    get_template_env,
    sanitize_name,
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

    def test_rejects_python_keyword(self) -> None:
        with pytest.raises(ValueError, match="reserved keyword"):
            _safe_identifier("class")

    def test_rejects_import_keyword(self) -> None:
        with pytest.raises(ValueError, match="reserved keyword"):
            _safe_identifier("import")


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


class TestSanitizeName:
    """Tests for the sanitize_name defense-in-depth function."""

    def test_valid_name(self) -> None:
        assert sanitize_name("Order") == "Order"

    def test_valid_snake_case(self) -> None:
        assert sanitize_name("audit_log") == "audit_log"

    def test_valid_single_char(self) -> None:
        assert sanitize_name("X") == "X"

    def test_rejects_path_traversal_unix(self) -> None:
        with pytest.raises(ValueError, match="path separator"):
            sanitize_name("../../etc/cron.d/backdoor")

    def test_rejects_path_traversal_relative(self) -> None:
        with pytest.raises(ValueError, match="path separator"):
            sanitize_name("../sibling")

    def test_rejects_absolute_path(self) -> None:
        with pytest.raises(ValueError, match="path separator"):
            sanitize_name("/etc/passwd")

    def test_rejects_dotdot_bare(self) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            sanitize_name("..")

    def test_rejects_special_chars(self) -> None:
        with pytest.raises(ValueError, match="Unsafe"):
            sanitize_name("Order;DROP")

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValueError, match="Unsafe"):
            sanitize_name("My Entity")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Unsafe"):
            sanitize_name("")

    def test_rejects_starts_with_number(self) -> None:
        with pytest.raises(ValueError, match="Unsafe"):
            sanitize_name("1Entity")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValueError, match="Unsafe"):
            sanitize_name("A" * 65)

    def test_custom_label_in_error(self) -> None:
        with pytest.raises(ValueError, match="entity name"):
            sanitize_name("../../bad", label="entity name")


class TestSanitizeNameInGenerators:
    """Integration-style tests verifying generators reject malicious names."""

    def _make_entity_mock(self, name: str) -> MagicMock:
        """Create a mock entity that bypasses Pydantic validation."""
        entity = MagicMock()
        entity.name = name
        entity.fields = []
        return entity

    def _make_domain_mock(self, name: str) -> MagicMock:
        """Create a mock domain that bypasses Pydantic validation."""
        domain = MagicMock()
        domain.name = name
        domain.entities = []
        return domain

    def test_generate_data_agent_rejects_traversal(self, tmp_path: Path) -> None:
        from ninja_codegen.generators.agents import generate_data_agent

        entity = self._make_entity_mock("../../etc/cron.d/backdoor")
        with pytest.raises(ValueError, match="path separator|Path traversal"):
            generate_data_agent(entity, tmp_path)

    def test_generate_domain_agent_rejects_traversal(self, tmp_path: Path) -> None:
        from ninja_codegen.generators.agents import generate_domain_agent

        domain = self._make_domain_mock("../../etc/cron.d/backdoor")
        with pytest.raises(ValueError, match="path separator|Path traversal"):
            generate_domain_agent(domain, tmp_path)

    def test_generate_model_rejects_traversal(self, tmp_path: Path) -> None:
        from ninja_codegen.generators.models import generate_model

        entity = self._make_entity_mock("../../etc/cron.d/backdoor")
        with pytest.raises(ValueError, match="path separator|Path traversal"):
            generate_model(entity, tmp_path)

    def test_generate_gql_type_rejects_traversal(self, tmp_path: Path) -> None:
        from ninja_codegen.generators.graphql import generate_gql_type

        entity = self._make_entity_mock("../../etc/cron.d/backdoor")
        with pytest.raises(ValueError, match="path separator|Path traversal"):
            generate_gql_type(entity, tmp_path)


class TestValidateOutputPath:
    def test_valid_path(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        file_path = output_dir / "entity.py"
        result = validate_output_path(output_dir, file_path)
        assert result.is_relative_to(output_dir.resolve())

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
        assert result.is_relative_to(output_dir.resolve())

    def test_rejects_prefix_trick(self, tmp_path: Path) -> None:
        """Regression: ensure /tmp/output_evil is not accepted for /tmp/output."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        evil_dir = tmp_path / "output_evil"
        evil_dir.mkdir()
        file_path = evil_dir / "entity.py"
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_output_path(output_dir, file_path)
