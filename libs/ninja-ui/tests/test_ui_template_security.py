"""Tests for template environment security in ninja-ui."""

from __future__ import annotations

from jinja2.sandbox import SandboxedEnvironment

from ninja_ui.crud.generator import _get_template_env as crud_env
from ninja_ui.chat.generator import _get_template_env as chat_env


class TestCrudTemplateEnvironment:
    """Verify ninja-ui CRUD generator uses secure template settings."""

    def test_environment_is_sandboxed(self):
        """CRUD template env must use SandboxedEnvironment."""
        env = crud_env()
        assert isinstance(env, SandboxedEnvironment)

    def test_autoescape_enabled_for_html(self):
        """Autoescape must be active for .html templates to prevent XSS."""
        env = crud_env()
        # select_autoescape returns a callable; verify it enables escaping for .html
        assert callable(env.autoescape)
        assert env.autoescape("template.html") is True

    def test_autoescape_disabled_for_non_html(self):
        """Autoescape should not be active for non-HTML templates."""
        env = crud_env()
        assert callable(env.autoescape)
        assert env.autoescape("template.txt") is False


class TestChatTemplateEnvironment:
    """Verify ninja-ui Chat generator uses secure template settings."""

    def test_environment_is_sandboxed(self):
        """Chat template env must use SandboxedEnvironment."""
        env = chat_env()
        assert isinstance(env, SandboxedEnvironment)

    def test_autoescape_enabled_for_html(self):
        """Autoescape must be active for .html templates to prevent XSS."""
        env = chat_env()
        assert callable(env.autoescape)
        assert env.autoescape("template.html") is True
