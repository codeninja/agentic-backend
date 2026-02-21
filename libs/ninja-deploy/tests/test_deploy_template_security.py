"""Tests for template environment security in ninja-deploy."""

from __future__ import annotations

from jinja2.sandbox import SandboxedEnvironment

from ninja_deploy.k8s_generator import _get_template_env


class TestK8sTemplateEnvironment:
    """Verify ninja-deploy K8s generator uses a sandboxed template environment."""

    def test_environment_is_sandboxed(self):
        """The K8s template env must use SandboxedEnvironment."""
        env = _get_template_env()
        assert isinstance(env, SandboxedEnvironment)

    def test_autoescape_disabled_for_yaml(self):
        """YAML templates should not have HTML autoescape enabled."""
        env = _get_template_env()
        assert env.autoescape is False
