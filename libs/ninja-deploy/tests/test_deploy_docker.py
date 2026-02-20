"""Tests for the Docker generator."""

from __future__ import annotations

from ninja_core.schema.project import AgenticSchema
from ninja_deploy.docker_generator import DEFAULT_APPS, DockerGenerator


class TestDockerGeneratorDockerfile:
    def test_dockerfile_contains_from_python(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        dockerfile = gen.generate_dockerfile("ninja-api")

        assert "FROM python:3.12-slim" in dockerfile

    def test_dockerfile_contains_app_name(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        dockerfile = gen.generate_dockerfile("ninja-api")

        assert "ninja-api" in dockerfile

    def test_dockerfile_multistage_build(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        dockerfile = gen.generate_dockerfile("ninja-api")

        assert "AS builder" in dockerfile
        assert "AS runtime" in dockerfile

    def test_dockerfile_non_root_user(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        dockerfile = gen.generate_dockerfile("ninja-api")

        assert "USER appuser" in dockerfile

    def test_dockerfile_expose_port(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        dockerfile = gen.generate_dockerfile("ninja-api", port="9000")

        assert "EXPOSE 9000" in dockerfile

    def test_dockerfile_custom_module(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        dockerfile = gen.generate_dockerfile("ninja-api", module="custom.app:create_app")

        assert "custom.app:create_app" in dockerfile

    def test_dockerfile_uses_uv(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        dockerfile = gen.generate_dockerfile("ninja-api")

        assert "uv" in dockerfile


class TestDockerGeneratorDockerignore:
    def test_dockerignore_excludes_git(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        ignore = gen.generate_dockerignore()

        assert ".git" in ignore

    def test_dockerignore_excludes_env(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        ignore = gen.generate_dockerignore()

        assert ".env" in ignore

    def test_dockerignore_excludes_pycache(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        ignore = gen.generate_dockerignore()

        assert "__pycache__" in ignore


class TestDockerGeneratorGenerateAll:
    def test_generate_all_includes_default_app(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        files = gen.generate_all()

        assert "ninja-api/Dockerfile" in files

    def test_generate_all_includes_dockerignore(self, sample_asd: AgenticSchema):
        gen = DockerGenerator(sample_asd)
        files = gen.generate_all()

        assert ".dockerignore" in files

    def test_generate_all_custom_apps(self, sample_asd: AgenticSchema):
        apps = [
            {"name": "api", "port": "8000", "module": "api.main:app"},
            {"name": "worker", "port": "9000", "module": "worker.main:app"},
        ]
        gen = DockerGenerator(sample_asd, apps=apps)
        files = gen.generate_all()

        assert "api/Dockerfile" in files
        assert "worker/Dockerfile" in files

    def test_write_dockerfiles_creates_files(self, sample_asd: AgenticSchema, tmp_path):
        gen = DockerGenerator(sample_asd)
        written = gen.write_dockerfiles(tmp_path)

        assert len(written) > 0
        for path in written:
            assert path.exists()


class TestDockerDefaultApps:
    def test_default_apps_has_ninja_api(self):
        names = [a["name"] for a in DEFAULT_APPS]
        assert "ninja-api" in names
