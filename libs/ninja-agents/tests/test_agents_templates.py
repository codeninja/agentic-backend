"""Tests for ninja_agents.templates path-traversal protection."""

import pytest

from ninja_agents.templates import TEMPLATES_DIR, get_template


class TestGetTemplate:
    """Tests for get_template()."""

    def test_load_valid_template(self):
        """Loading a known template returns non-empty content."""
        content = get_template("data_agent")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_all_bundled_templates(self):
        """Every .yaml file in the templates dir is loadable."""
        for yaml_file in TEMPLATES_DIR.glob("*.yaml"):
            name = yaml_file.stem
            content = get_template(name)
            assert content, f"Template {name} should not be empty"

    def test_hyphen_and_underscore_allowed(self):
        """Names with hyphens and underscores are valid."""
        # coordinator_agent uses underscore, data_agent uses underscore
        content = get_template("coordinator_agent")
        assert len(content) > 0

    def test_missing_template_raises_file_not_found(self):
        """A valid name that doesn't exist raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            get_template("nonexistent-template-xyz")

    @pytest.mark.parametrize(
        "malicious_name",
        [
            "../../../../etc/passwd",
            "../../../etc/shadow",
            "..%2F..%2Fetc%2Fpasswd",
            "../__init__",
            "./data_agent",
            "data_agent/../../etc/passwd",
            "foo/../bar",
        ],
    )
    def test_path_traversal_rejected(self, malicious_name: str):
        """Path traversal attempts are rejected with ValueError."""
        with pytest.raises(ValueError, match="Invalid template name"):
            get_template(malicious_name)

    @pytest.mark.parametrize(
        "invalid_name",
        [
            "",
            " ",
            "name with spaces",
            "name\ttab",
            "name\nnewline",
            "name;injection",
            "name|pipe",
            "name$var",
            "name`backtick`",
        ],
    )
    def test_invalid_characters_rejected(self, invalid_name: str):
        """Names with special characters are rejected."""
        with pytest.raises(ValueError, match="Invalid template name"):
            get_template(invalid_name)

    def test_null_byte_rejected(self):
        """Null bytes in template names are rejected."""
        with pytest.raises(ValueError, match="Invalid template name"):
            get_template("data_agent\x00.py")
