"""Tests for the Helm chart generator."""

from __future__ import annotations

import yaml
from ninja_core.schema.project import AgenticSchema
from ninja_deploy.helm_generator import ENV_PROFILES, INFRA_CHART_MAP, HelmGenerator


class TestHelmGeneratorChart:
    def test_chart_yaml_has_project_name(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        chart = gen.generate_chart_yaml()
        parsed = yaml.safe_load(chart)

        assert parsed["name"] == "test-shop"
        assert parsed["apiVersion"] == "v2"

    def test_chart_yaml_has_all_dependencies(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        chart = gen.generate_chart_yaml()
        parsed = yaml.safe_load(chart)

        dep_names = {d["name"] for d in parsed["dependencies"]}
        assert dep_names == {"postgresql", "mongodb", "neo4j", "milvus"}

    def test_chart_yaml_sql_only(self, sql_only_asd: AgenticSchema):
        gen = HelmGenerator(sql_only_asd)
        chart = gen.generate_chart_yaml()
        parsed = yaml.safe_load(chart)

        dep_names = {d["name"] for d in parsed["dependencies"]}
        assert dep_names == {"postgresql"}

    def test_dependencies_have_version_and_repo(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        chart = gen.generate_chart_yaml()
        parsed = yaml.safe_load(chart)

        for dep in parsed["dependencies"]:
            assert "version" in dep
            assert "repository" in dep


class TestHelmGeneratorValues:
    def test_dev_values_single_replica(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("dev")
        parsed = yaml.safe_load(values)

        assert parsed["replicaCount"] == 1

    def test_prod_values_three_replicas(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("prod")
        parsed = yaml.safe_load(values)

        assert parsed["replicaCount"] == 3

    def test_staging_values_two_replicas(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("staging")
        parsed = yaml.safe_load(values)

        assert parsed["replicaCount"] == 2

    def test_values_contains_postgresql_when_sql(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("dev")
        parsed = yaml.safe_load(values)

        assert "postgresql" in parsed
        assert parsed["postgresql"]["enabled"] is True

    def test_values_contains_mongodb_when_mongo(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("dev")
        parsed = yaml.safe_load(values)

        assert "mongodb" in parsed
        assert parsed["mongodb"]["enabled"] is True

    def test_values_contains_milvus_when_vector(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("dev")
        parsed = yaml.safe_load(values)

        assert "milvus" in parsed
        assert parsed["milvus"]["enabled"] is True

    def test_values_contains_neo4j_when_graph(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("dev")
        parsed = yaml.safe_load(values)

        assert "neo4j" in parsed
        assert parsed["neo4j"]["enabled"] is True

    def test_sql_only_no_mongo_section(self, sql_only_asd: AgenticSchema):
        gen = HelmGenerator(sql_only_asd)
        values = gen.generate_values_yaml("dev")
        parsed = yaml.safe_load(values)

        assert "postgresql" in parsed
        assert "mongodb" not in parsed
        assert "neo4j" not in parsed
        assert "milvus" not in parsed

    def test_values_has_resource_limits(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        values = gen.generate_values_yaml("prod")
        parsed = yaml.safe_load(values)

        assert "resources" in parsed
        assert parsed["resources"]["requests"]["cpu"] == "500m"
        assert parsed["resources"]["limits"]["memory"] == "2Gi"


class TestHelmGeneratorTemplates:
    def test_deployment_template_renders(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        deployment = gen.generate_deployment_template()

        assert "Deployment" in deployment
        assert "test-shop" in deployment

    def test_service_template_renders(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        service = gen.generate_service_template()

        assert "Service" in service
        assert "test-shop" in service

    def test_helpers_template_renders(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        helpers = gen.generate_helpers_template()

        assert "test-shop.fullname" in helpers
        assert "test-shop.labels" in helpers
        assert "test-shop.selectorLabels" in helpers


class TestHelmGeneratorGenerateAll:
    def test_generate_all_includes_chart_yaml(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        files = gen.generate_all()

        assert "test-shop/Chart.yaml" in files

    def test_generate_all_includes_all_env_values(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        files = gen.generate_all()

        assert "test-shop/values.yaml" in files
        assert "test-shop/values-dev.yaml" in files
        assert "test-shop/values-staging.yaml" in files
        assert "test-shop/values-prod.yaml" in files

    def test_generate_all_includes_templates(self, sample_asd: AgenticSchema):
        gen = HelmGenerator(sample_asd)
        files = gen.generate_all()

        assert "test-shop/templates/deployment.yaml" in files
        assert "test-shop/templates/service.yaml" in files
        assert "test-shop/templates/_helpers.tpl" in files

    def test_write_chart_creates_files(self, sample_asd: AgenticSchema, tmp_path):
        gen = HelmGenerator(sample_asd)
        written = gen.write_chart(tmp_path)

        assert len(written) > 0
        for path in written:
            assert path.exists()


class TestHelmInfraMapping:
    def test_infra_chart_map_covers_all_engines(self):
        for engine in [e for e in INFRA_CHART_MAP]:
            assert "name" in INFRA_CHART_MAP[engine]
            assert "version" in INFRA_CHART_MAP[engine]
            assert "repository" in INFRA_CHART_MAP[engine]

    def test_env_profiles_have_required_keys(self):
        for env_name, profile in ENV_PROFILES.items():
            assert "replicas" in profile
            assert "cpu_request" in profile
            assert "memory_request" in profile
            assert "cpu_limit" in profile
            assert "memory_limit" in profile
