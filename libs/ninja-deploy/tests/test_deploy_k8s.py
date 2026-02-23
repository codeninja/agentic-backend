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


class TestK8sDeploymentSecurityContext:
    """Tests for pod and container security contexts on app deployments."""

    def test_pod_runs_as_non_root(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        pod_sec = parsed["spec"]["template"]["spec"]["securityContext"]
        assert pod_sec["runAsNonRoot"] is True

    def test_pod_runs_as_user_1000(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        pod_sec = parsed["spec"]["template"]["spec"]["securityContext"]
        assert pod_sec["runAsUser"] == 1000
        assert pod_sec["runAsGroup"] == 1000

    def test_container_no_privilege_escalation(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        container = parsed["spec"]["template"]["spec"]["containers"][0]
        sec_ctx = container["securityContext"]
        assert sec_ctx["allowPrivilegeEscalation"] is False

    def test_container_read_only_root_fs(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        container = parsed["spec"]["template"]["spec"]["containers"][0]
        sec_ctx = container["securityContext"]
        assert sec_ctx["readOnlyRootFilesystem"] is True

    def test_container_drops_all_capabilities(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        parsed = yaml.safe_load(deployment)

        container = parsed["spec"]["template"]["spec"]["containers"][0]
        caps = container["securityContext"]["capabilities"]
        assert "ALL" in caps["drop"]


class TestK8sDeploymentImageTag:
    """Tests for image tag handling — no more 'latest' by default."""

    def test_default_image_tag_is_placeholder(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment()
        assert "SET_IMAGE_TAG" in deployment
        assert ":latest" not in deployment

    def test_custom_image_tag(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        deployment = gen.generate_deployment(image_tag="v1.2.3")
        assert "v1.2.3" in deployment


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

    def test_secret_uses_env_var_placeholders_not_changeme(self, sample_asd: AgenticSchema):
        """Secrets must use env-var placeholders instead of hardcoded 'changeme'."""
        gen = K8sGenerator(sample_asd)
        secret = gen.generate_secret()
        assert "changeme" not in secret
        assert "${POSTGRES_PASSWORD}" in secret
        assert "${NEO4J_PASSWORD}" in secret

    def test_secret_has_placeholder_warning_annotation(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        secret = gen.generate_secret()
        parsed = yaml.safe_load(secret)
        assert "ninja-deploy/placeholder-warning" in parsed["metadata"]["annotations"]


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


class TestK8sInfraSecurityContext:
    """Tests for pod security contexts on infrastructure deployments."""

    def test_infra_pods_run_as_non_root(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        for name, content in infra.items():
            docs = list(yaml.safe_load_all(content))
            deployment = next(d for d in docs if d["kind"] == "Deployment")
            pod_sec = deployment["spec"]["template"]["spec"]["securityContext"]
            assert pod_sec["runAsNonRoot"] is True, f"{name} missing runAsNonRoot"

    def test_infra_containers_drop_all_capabilities(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        for name, content in infra.items():
            docs = list(yaml.safe_load_all(content))
            deployment = next(d for d in docs if d["kind"] == "Deployment")
            container = deployment["spec"]["template"]["spec"]["containers"][0]
            caps = container["securityContext"]["capabilities"]
            assert "ALL" in caps["drop"], f"{name} missing capabilities.drop ALL"

    def test_infra_containers_no_privilege_escalation(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        for name, content in infra.items():
            docs = list(yaml.safe_load_all(content))
            deployment = next(d for d in docs if d["kind"] == "Deployment")
            container = deployment["spec"]["template"]["spec"]["containers"][0]
            assert container["securityContext"]["allowPrivilegeEscalation"] is False

    def test_postgres_runs_as_uid_70(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        docs = list(yaml.safe_load_all(infra["postgresql.yaml"]))
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        assert deployment["spec"]["template"]["spec"]["securityContext"]["runAsUser"] == 70

    def test_mongo_runs_as_uid_999(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        docs = list(yaml.safe_load_all(infra["mongodb.yaml"]))
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        assert deployment["spec"]["template"]["spec"]["securityContext"]["runAsUser"] == 999

    def test_neo4j_runs_as_uid_7474(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        docs = list(yaml.safe_load_all(infra["neo4j.yaml"]))
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        assert deployment["spec"]["template"]["spec"]["securityContext"]["runAsUser"] == 7474

    def test_milvus_runs_as_uid_1000(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        docs = list(yaml.safe_load_all(infra["milvus.yaml"]))
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        assert deployment["spec"]["template"]["spec"]["securityContext"]["runAsUser"] == 1000


class TestK8sInfraResourceLimits:
    """Tests for resource limits on infra pods."""

    def test_infra_pods_have_resource_limits(self, sample_asd: AgenticSchema):
        gen = K8sGenerator(sample_asd)
        infra = gen.generate_infra_deployments()
        for name, content in infra.items():
            docs = list(yaml.safe_load_all(content))
            deployment = next(d for d in docs if d["kind"] == "Deployment")
            container = deployment["spec"]["template"]["spec"]["containers"][0]
            assert "resources" in container, f"{name} missing resources"
            assert "requests" in container["resources"]
            assert "limits" in container["resources"]
            assert "cpu" in container["resources"]["requests"]
            assert "memory" in container["resources"]["requests"]


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
        required = {
            "name",
            "image",
            "port",
            "run_as_user",
            "run_as_group",
            "read_only_fs",
            "cpu_request",
            "memory_request",
            "cpu_limit",
            "memory_limit",
        }
        for engine, info in INFRA_IMAGES.items():
            assert required.issubset(info.keys()), f"{engine} missing keys"


class TestK8sPlaceholderCredentials:
    def test_generate_all_succeeds_without_changeme(self, sample_asd):
        """Templates now use env-var placeholders, so generate_all() should succeed."""
        gen = K8sGenerator(sample_asd)
        files = gen.generate_all()
        assert len(files) > 0

    def test_raises_when_changeme_present(self):
        """If 'changeme' is manually injected, PlaceholderCredentialError is raised."""
        files = {"secret.yaml": "password: changeme\n"}
        locations = K8sGenerator._check_placeholder_credentials(files)
        assert len(locations) > 0

    def test_allow_placeholder_creds_suppresses_error(self, sample_asd):
        """With allow_placeholder_creds=True, changeme triggers a warning not an error."""
        K8sGenerator(sample_asd)
        # Inject changeme into a file to test the warning path
        files = {"test.yaml": "password: changeme\n"}
        locations = K8sGenerator._check_placeholder_credentials(files)
        assert len(locations) > 0

    def test_check_placeholder_detects_changeme(self):
        files = {"secret.yaml": "POSTGRES_PASSWORD: changeme\nNEO4J_AUTH: neo4j/changeme\n"}
        locations = K8sGenerator._check_placeholder_credentials(files)
        assert len(locations) == 2

    def test_no_warnings_when_no_placeholders(self):
        files = {"clean.yaml": "apiVersion: v1\nkind: Secret\ndata:\n  key: real-password\n"}
        locations = K8sGenerator._check_placeholder_credentials(files)
        assert len(locations) == 0

    def test_secret_template_no_changeme(self, sample_asd):
        """Verify the secret template itself no longer contains 'changeme'."""
        gen = K8sGenerator(sample_asd)
        secret = gen.generate_secret()
        assert "changeme" not in secret


class TestK8sLatestTagWarning:
    def test_check_latest_tag_detects_latest(self):
        files = {"deploy.yaml": "image: myapp:latest\n"}
        locations = K8sGenerator._check_latest_tag(files)
        assert len(locations) > 0

    def test_check_latest_tag_clean(self):
        files = {"deploy.yaml": "image: myapp:v1.2.3\n"}
        locations = K8sGenerator._check_latest_tag(files)
        assert len(locations) == 0
