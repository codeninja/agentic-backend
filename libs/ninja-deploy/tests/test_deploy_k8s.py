"""Tests for the raw K8s manifest generator."""

from __future__ import annotations

import yaml
from ninja_core.schema.project import AgenticSchema
from ninja_deploy.k8s_generator import INFRA_IMAGES, K8sGenerator


class TestK8sGeneratorDeployment:
    def test_deployment_kind(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        assert parsed["kind"] == "Deployment"

    def test_deployment_has_project_label(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        assert parsed["metadata"]["labels"]["project"] == "test-shop"

    def test_deployment_default_app_name(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        assert parsed["metadata"]["name"] == "ninja-api"

    def test_deployment_custom_app_name(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment(app_name="my-app", port="9000")
        parsed = yaml.safe_load(deployment)

        assert parsed["metadata"]["name"] == "my-app"

    def test_deployment_has_health_probes(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        container = parsed["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        assert "readinessProbe" in container

    def test_deployment_has_resource_limits(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        container = parsed["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "requests" in container["resources"]
        assert "limits" in container["resources"]

    def test_deployment_has_env_from(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        container = parsed["spec"]["template"]["spec"]["containers"][0]
        assert "envFrom" in container


class TestK8sGeneratorService:
    def test_service_kind(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        service = gen.generate_service()
        parsed = yaml.safe_load(service)

        assert parsed["kind"] == "Service"

    def test_service_type_clusterip(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        service = gen.generate_service()
        parsed = yaml.safe_load(service)

        assert parsed["spec"]["type"] == "ClusterIP"

    def test_service_port_matches(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        service = gen.generate_service(port="3000")
        parsed = yaml.safe_load(service)

        assert parsed["spec"]["ports"][0]["port"] == 3000


class TestK8sGeneratorConfigMap:
    def test_configmap_kind(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        cm = gen.generate_configmap()
        parsed = yaml.safe_load(cm)

        assert parsed["kind"] == "ConfigMap"

    def test_configmap_has_postgres_when_sql(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        cm = gen.generate_configmap()
        parsed = yaml.safe_load(cm)

        assert "POSTGRES_HOST" in parsed["data"]

    def test_configmap_has_mongo_when_mongo(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        cm = gen.generate_configmap()
        parsed = yaml.safe_load(cm)

        assert "MONGO_HOST" in parsed["data"]

    def test_configmap_has_neo4j_when_graph(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        cm = gen.generate_configmap()
        parsed = yaml.safe_load(cm)

        assert "NEO4J_HOST" in parsed["data"]

    def test_configmap_has_milvus_when_vector(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        cm = gen.generate_configmap()
        parsed = yaml.safe_load(cm)

        assert "MILVUS_HOST" in parsed["data"]

    def test_configmap_sql_only(self, sql_only_asd: AgenticSchema):
        gen = K8sGenerator(sql_only_asd)
        cm = gen.generate_configmap()
        parsed = yaml.safe_load(cm)

        assert "POSTGRES_HOST" in parsed["data"]
        assert "MONGO_HOST" not in parsed["data"]


class TestK8sGeneratorSecret:
    def test_secret_kind(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        secret = gen.generate_secret()
        parsed = yaml.safe_load(secret)

        assert parsed["kind"] == "Secret"

    def test_secret_type_opaque(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        secret = gen.generate_secret()
        parsed = yaml.safe_load(secret)

        assert parsed["type"] == "Opaque"

    def test_secret_has_postgres_creds_when_sql(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        secret = gen.generate_secret()
        parsed = yaml.safe_load(secret)

        assert "POSTGRES_PASSWORD" in parsed["stringData"]

    def test_secret_has_neo4j_auth_when_graph(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        secret = gen.generate_secret()
        parsed = yaml.safe_load(secret)

        assert "NEO4J_AUTH" in parsed["stringData"]


class TestK8sGeneratorInfra:
    def test_generates_infra_for_all_engines(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()

        assert "postgresql.yaml" in infra
        assert "mongodb.yaml" in infra
        assert "neo4j.yaml" in infra
        assert "milvus.yaml" in infra

    def test_infra_contains_deployment_and_service(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()

        for content in infra.values():
            assert "Deployment" in content
            assert "Service" in content

    def test_sql_only_generates_only_postgres(self, sql_only_asd: AgenticSchema):
        gen = K8sGenerator(sql_only_asd)
        infra = gen.generate_infra_deployments()

        assert "postgresql.yaml" in infra
        assert len(infra) == 1


class TestK8sGeneratorGenerateAll:
    def test_generate_all_includes_core_manifests(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        files = gen.generate_all()

        assert "deployment.yaml" in files
        assert "service.yaml" in files
        assert "configmap.yaml" in files
        assert "secret.yaml" in files

    def test_generate_all_includes_infra(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        files = gen.generate_all()

        infra_files = [k for k in files if k.startswith("infra/")]
        assert len(infra_files) == 4

    def test_write_manifests_creates_files(self, sample_asd: AgenticSchema, tmp_path):
        gen = K8sGenerator(sample_asd)
        written = gen.write_manifests(tmp_path)

        assert len(written) > 0
        for path in written:
            assert path.exists()


class TestK8sInfraImages:
    def test_infra_images_have_required_keys(self):
        for engine, info in INFRA_IMAGES.items():
            assert "name" in info
            assert "image" in info
            assert "port" in info
