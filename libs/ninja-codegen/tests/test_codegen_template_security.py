"""Tests for template environment security in ninja-codegen."""

from __future__ import annotations

from jinja2.sandbox import SandboxedEnvironment

from ninja_codegen.generators.base import get_template_env


class TestCodegenTemplateEnvironment:
    """Verify ninja-codegen uses a sandboxed template environment."""

    def test_environment_is_sandboxed(self):
        """The codegen template env must use SandboxedEnvironment."""
        env = get_template_env()
        assert isinstance(env, SandboxedEnvironment)

    def test_repr_filter_preserved(self):
        """Custom 'repr' filter should still be available."""
        env = get_template_env()
        assert "repr" in env.filters
