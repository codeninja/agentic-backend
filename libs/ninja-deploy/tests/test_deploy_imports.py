"""Tests for ninja-deploy package imports."""

from __future__ import annotations


class TestDeployImports:
    def test_import_package(self):
        import ninja_deploy

        assert ninja_deploy is not None

    def test_import_helm_generator(self):
        from ninja_deploy import HelmGenerator

        assert HelmGenerator is not None

    def test_import_docker_generator(self):
        from ninja_deploy import DockerGenerator

        assert DockerGenerator is not None

    def test_import_k8s_generator(self):
        from ninja_deploy import K8sGenerator

        assert K8sGenerator is not None

    def test_import_ci_generator(self):
        from ninja_deploy import CIGenerator

        assert CIGenerator is not None
