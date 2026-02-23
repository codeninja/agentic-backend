"""ASD-driven raw Kubernetes manifest generator."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from ninja_core.schema.entity import StorageEngine
from ninja_core.schema.project import AgenticSchema

logger = logging.getLogger(__name__)

_PLACEHOLDER_PATTERN = re.compile(r"changeme", re.IGNORECASE)
_LATEST_TAG_PATTERN = re.compile(r"image:\s*\S+:latest", re.MULTILINE)


class PlaceholderCredentialError(ValueError):
    """Raised when generated manifests still contain placeholder credentials."""


# Maps storage engines to infra container images used in raw K8s manifests.
# run_as_user / run_as_group follow upstream image conventions:
#   - PostgreSQL: UID 70 (official postgres alpine)
#   - MongoDB: UID 999 (official mongo image)
#   - Neo4j: UID 7474 (official neo4j community image)
#   - Milvus: UID 1000 (milvusdb image)
INFRA_IMAGES: dict[StorageEngine, dict[str, str]] = {
    StorageEngine.SQL: {
        "name": "postgresql",
        "image": "postgres:16-alpine",
        "port": "5432",
        "run_as_user": "70",
        "run_as_group": "70",
        "read_only_fs": "false",
        "cpu_request": "100m",
        "memory_request": "256Mi",
        "cpu_limit": "500m",
        "memory_limit": "512Mi",
    },
    StorageEngine.MONGO: {
        "name": "mongodb",
        "image": "mongo:7",
        "port": "27017",
        "run_as_user": "999",
        "run_as_group": "999",
        "read_only_fs": "false",
        "cpu_request": "100m",
        "memory_request": "256Mi",
        "cpu_limit": "500m",
        "memory_limit": "512Mi",
    },
    StorageEngine.GRAPH: {
        "name": "neo4j",
        "image": "neo4j:5-community",
        "port": "7687",
        "run_as_user": "7474",
        "run_as_group": "7474",
        "read_only_fs": "false",
        "cpu_request": "200m",
        "memory_request": "512Mi",
        "cpu_limit": "1000m",
        "memory_limit": "1Gi",
    },
    StorageEngine.VECTOR: {
        "name": "milvus",
        "image": "milvusdb/milvus:v2.4.0",
        "port": "19530",
        "run_as_user": "1000",
        "run_as_group": "1000",
        "read_only_fs": "false",
        "cpu_request": "200m",
        "memory_request": "256Mi",
        "cpu_limit": "1000m",
        "memory_limit": "1Gi",
    },
}


def _get_template_env() -> Environment:
    return Environment(
        loader=PackageLoader("ninja_deploy", "templates/k8s"),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


class K8sGenerator:
    """Generates raw Kubernetes manifests from an ASD."""

    def __init__(self, schema: AgenticSchema) -> None:
        self.schema = schema
        self.env = _get_template_env()

    def _required_engines(self) -> set[StorageEngine]:
        return {e.storage_engine for e in self.schema.entities}

    def _infra_services(self) -> list[dict[str, str]]:
        """Build list of infra services needed."""
        services: list[dict[str, str]] = []
        for engine in sorted(self._required_engines(), key=lambda e: e.value):
            if engine in INFRA_IMAGES:
                services.append(INFRA_IMAGES[engine])
        return services

    def generate_deployment(
        self,
        app_name: str = "ninja-api",
        port: str = "8000",
        image_tag: str = "SET_IMAGE_TAG",
    ) -> str:
        """Generate a Deployment manifest for the app.

        Args:
            app_name: Name of the application container.
            port: Container port to expose.
            image_tag: Docker image tag. Defaults to a placeholder that must be
                explicitly set before deploying.
        """
        template = self.env.get_template("deployment.yaml.j2")
        return template.render(
            project_name=self.schema.project_name,
            app_name=app_name,
            port=port,
            image_tag=image_tag,
        )

    def generate_service(self, app_name: str = "ninja-api", port: str = "8000") -> str:
        """Generate a Service manifest for the app."""
        template = self.env.get_template("service.yaml.j2")
        return template.render(
            project_name=self.schema.project_name,
            app_name=app_name,
            port=port,
        )

    def generate_configmap(self) -> str:
        """Generate a ConfigMap with storage engine connection info."""
        template = self.env.get_template("configmap.yaml.j2")
        engines = self._required_engines()
        return template.render(
            project_name=self.schema.project_name,
            engines=engines,
            StorageEngine=StorageEngine,
        )

    def generate_secret(self) -> str:
        """Generate a Secret manifest with placeholder credentials."""
        template = self.env.get_template("secret.yaml.j2")
        engines = self._required_engines()
        return template.render(
            project_name=self.schema.project_name,
            engines=engines,
            StorageEngine=StorageEngine,
        )

    def generate_infra_deployments(self) -> dict[str, str]:
        """Generate Deployment + Service manifests for each infra dependency."""
        template = self.env.get_template("infra.yaml.j2")
        manifests: dict[str, str] = {}
        for svc in self._infra_services():
            manifests[f"{svc['name']}.yaml"] = template.render(
                project_name=self.schema.project_name,
                svc=svc,
            )
        return manifests

    @staticmethod
    def _check_placeholder_credentials(files: dict[str, str]) -> list[str]:
        """Find any placeholder credentials ('changeme') in generated manifests.

        Returns a list of ``filename:line`` location strings.
        """
        locations: list[str] = []
        for filename, content in files.items():
            for match in _PLACEHOLDER_PATTERN.finditer(content):
                line_num = content[: match.start()].count("\n") + 1
                locations.append(f"{filename}:{line_num}")
        return locations

    @staticmethod
    def _check_latest_tag(files: dict[str, str]) -> list[str]:
        """Find any image references using the ``latest`` tag."""
        locations: list[str] = []
        for filename, content in files.items():
            for match in _LATEST_TAG_PATTERN.finditer(content):
                line_num = content[: match.start()].count("\n") + 1
                locations.append(f"{filename}:{line_num}")
        return locations

    def generate_all(
        self,
        app_name: str = "ninja-api",
        port: str = "8000",
        *,
        allow_placeholder_creds: bool = False,
    ) -> dict[str, str]:
        """Generate all raw K8s manifests. Returns dict of relative_path -> content.

        Args:
            app_name: The application deployment name.
            port: Container port to expose.
            allow_placeholder_creds: If ``True``, skip the hard error when placeholder
                credentials (``changeme``) are detected.  Intended only for local
                development.

        Raises:
            PlaceholderCredentialError: If placeholder credentials are detected and
                *allow_placeholder_creds* is ``False``.
        """
        files: dict[str, str] = {}
        files["deployment.yaml"] = self.generate_deployment(app_name, port)
        files["service.yaml"] = self.generate_service(app_name, port)
        files["configmap.yaml"] = self.generate_configmap()
        files["secret.yaml"] = self.generate_secret()

        for name, content in self.generate_infra_deployments().items():
            files[f"infra/{name}"] = content

        # Validate: placeholder credentials
        cred_locations = self._check_placeholder_credentials(files)
        if cred_locations:
            msg = (
                "Generated manifests contain placeholder credentials ('changeme') "
                f"that MUST be replaced before deployment: {', '.join(cred_locations)}"
            )
            if allow_placeholder_creds:
                logger.warning(msg)
            else:
                raise PlaceholderCredentialError(msg)

        # Validate: 'latest' tags
        tag_locations = self._check_latest_tag(files)
        if tag_locations:
            logger.warning(
                "Generated manifests reference 'latest' image tag at: %s. "
                "Pin to a specific version for production use.",
                ", ".join(tag_locations),
            )

        return files

    def write_manifests(
        self,
        output_dir: Path,
        *,
        allow_placeholder_creds: bool = False,
    ) -> list[Path]:
        """Write all K8s manifests to disk, return list of written paths."""
        written: list[Path] = []
        for rel_path, content in self.generate_all(
            allow_placeholder_creds=allow_placeholder_creds,
        ).items():
            full_path = output_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(full_path)
        return written
