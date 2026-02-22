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

# Maps storage engines to infra container images used in raw K8s manifests
INFRA_IMAGES: dict[StorageEngine, dict[str, str]] = {
    StorageEngine.SQL: {"name": "postgresql", "image": "postgres:16-alpine", "port": "5432"},
    StorageEngine.MONGO: {"name": "mongodb", "image": "mongo:7", "port": "27017"},
    StorageEngine.GRAPH: {"name": "neo4j", "image": "neo4j:5-community", "port": "7687"},
    StorageEngine.VECTOR: {"name": "milvus", "image": "milvusdb/milvus:v2.4.0", "port": "19530"},
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

    def generate_deployment(self, app_name: str = "ninja-api", port: str = "8000") -> str:
        """Generate a Deployment manifest for the app."""
        template = self.env.get_template("deployment.yaml.j2")
        return template.render(
            project_name=self.schema.project_name,
            app_name=app_name,
            port=port,
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
    def _warn_placeholder_credentials(files: dict[str, str]) -> list[str]:
        """Emit warnings for any placeholder credentials found in generated manifests."""
        warnings: list[str] = []
        for filename, content in files.items():
            for match in _PLACEHOLDER_PATTERN.finditer(content):
                line_num = content[: match.start()].count("\n") + 1
                warnings.append(f"{filename}:{line_num}")
        if warnings:
            logger.warning(
                "Generated manifests contain placeholder credentials ('changeme') "
                "that MUST be replaced before deployment: %s",
                ", ".join(warnings),
            )
        return warnings

    def generate_all(self, app_name: str = "ninja-api", port: str = "8000") -> dict[str, str]:
        """Generate all raw K8s manifests. Returns dict of relative_path -> content."""
        files: dict[str, str] = {}
        files["deployment.yaml"] = self.generate_deployment(app_name, port)
        files["service.yaml"] = self.generate_service(app_name, port)
        files["configmap.yaml"] = self.generate_configmap()
        files["secret.yaml"] = self.generate_secret()

        for name, content in self.generate_infra_deployments().items():
            files[f"infra/{name}"] = content

        self._warn_placeholder_credentials(files)
        return files

    def write_manifests(self, output_dir: Path) -> list[Path]:
        """Write all K8s manifests to disk, return list of written paths."""
        written: list[Path] = []
        for rel_path, content in self.generate_all().items():
            full_path = output_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(full_path)
        return written
