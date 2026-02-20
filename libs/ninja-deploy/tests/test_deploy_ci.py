"""Tests for the CI/CD workflow generator."""

from __future__ import annotations

import yaml
from ninja_core.schema.project import AgenticSchema
from ninja_deploy.ci_generator import CIGenerator


class TestCIGeneratorDeploy:
    def test_deploy_workflow_name(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        assert "Deploy" in parsed["name"]

    def test_deploy_workflow_triggers_on_main(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        # PyYAML parses bare `on` as boolean True
        assert "main" in parsed[True]["push"]["branches"]

    def test_deploy_workflow_has_test_job(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        assert "test" in parsed["jobs"]

    def test_deploy_workflow_has_build_job(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        assert "build" in parsed["jobs"]

    def test_deploy_workflow_has_deploy_job(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        assert "deploy" in parsed["jobs"]

    def test_deploy_job_depends_on_build(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        assert "build" in parsed["jobs"]["deploy"]["needs"]

    def test_build_job_depends_on_test(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        assert "test" in parsed["jobs"]["build"]["needs"]

    def test_deploy_workflow_custom_registry(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd, registry="docker.io")
        workflow = gen.generate_deploy_workflow()
        parsed = yaml.safe_load(workflow)

        assert parsed["env"]["REGISTRY"] == "docker.io"

    def test_deploy_workflow_custom_apps(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd, apps=["api", "worker"])
        workflow = gen.generate_deploy_workflow()

        assert "api" in workflow
        assert "worker" in workflow

    def test_deploy_workflow_uses_helm(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_deploy_workflow()

        assert "helm" in workflow.lower()


class TestCIGeneratorTest:
    def test_test_workflow_name(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_test_workflow()
        parsed = yaml.safe_load(workflow)

        assert "Test" in parsed["name"]

    def test_test_workflow_triggers_on_pr(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_test_workflow()
        parsed = yaml.safe_load(workflow)

        # PyYAML parses bare `on` as boolean True
        assert "pull_request" in parsed[True]

    def test_test_workflow_has_lint_step(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_test_workflow()

        assert "ruff" in workflow

    def test_test_workflow_has_pytest_step(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_test_workflow()

        assert "pytest" in workflow

    def test_test_workflow_uses_uv(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        workflow = gen.generate_test_workflow()

        assert "uv" in workflow


class TestCIGeneratorGenerateAll:
    def test_generate_all_includes_deploy(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        files = gen.generate_all()

        assert "deploy.yml" in files

    def test_generate_all_includes_test(self, sample_asd: AgenticSchema):
        gen = CIGenerator(sample_asd)
        files = gen.generate_all()

        assert "test.yml" in files

    def test_write_workflows_creates_files(self, sample_asd: AgenticSchema, tmp_path):
        gen = CIGenerator(sample_asd)
        written = gen.write_workflows(tmp_path)

        assert len(written) == 2
        for path in written:
            assert path.exists()
