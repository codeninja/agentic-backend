"""ASD-driven Helm chart generator."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from ninja_core.schema.entity import StorageEngine
from ninja_core.schema.project import AgenticSchema

logger = logging.getLogger(__name__)

_PLACEHOLDER_PATTERN = re.compile(r"changeme", re.IGNORECASE)
_LATEST_TAG_PATTERN = re.compile(r":\s*[\"']?latest[\"']?\s*$", re.MULTILINE)


class PlaceholderCredentialError(ValueError):
    """Raised when generated manifests still contain placeholder credentials."""

# Maps ASD storage engines to Helm dependency charts
INFRA_CHART_MAP: dict[StorageEngine, dict[str, str]] = {
    StorageEngine.SQL: {
        "name": "postgresql",
        "version": "16.4.1",
        "repository": "https://charts.bitnami.com/bitnami",
    },
    StorageEngine.MONGO: {
        "name": "mongodb",
        "version": "16.4.0",
        "repository": "https://charts.bitnami.com/bitnami",
    },
    StorageEngine.GRAPH: {
        "name": "neo4j",
        "version": "5.25.1",
        "repository": "https://helm.neo4j.com/neo4j",
    },
    StorageEngine.VECTOR: {
        "name": "milvus",
        "version": "4.2.8",
        "repository": "https://zilliztech.github.io/milvus-helm",
    },
}

# Default resource profiles per environment
ENV_PROFILES: dict[str, dict[str, str]] = {
    "dev": {
        "replicas": "1",
        "cpu_request": "100m",
        "memory_request": "128Mi",
        "cpu_limit": "500m",
        "memory_limit": "512Mi",
    },
    "staging": {
        "replicas": "2",
        "cpu_request": "250m",
        "memory_request": "256Mi",
        "cpu_limit": "1000m",
        "memory_limit": "1Gi",
    },
    "prod": {
        "replicas": "3",
        "cpu_request": "500m",
        "memory_request": "512Mi",
        "cpu_limit": "2000m",
        "memory_limit": "2Gi",
    },
}


def _get_template_env() -> Environment:
    return Environment(
        loader=PackageLoader("ninja_deploy", "templates/helm"),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


class HelmGenerator:
    """Generates Helm charts from an ASD."""

    def __init__(self, schema: AgenticSchema) -> None:
        self.schema = schema
        self.env = _get_template_env()

    def _required_engines(self) -> set[StorageEngine]:
        """Collect unique storage engines declared in the ASD."""
        return {e.storage_engine for e in self.schema.entities}

    def _infra_dependencies(self) -> list[dict[str, str]]:
        """Build Helm chart dependency list from required engines."""
        deps: list[dict[str, str]] = []
        for engine in sorted(self._required_engines(), key=lambda e: e.value):
            if engine in INFRA_CHART_MAP:
                deps.append(INFRA_CHART_MAP[engine])
        return deps

    def generate_chart_yaml(self) -> str:
        """Generate Chart.yaml content."""
        template = self.env.get_template("Chart.yaml.j2")
        return template.render(
            project_name=self.schema.project_name,
            dependencies=self._infra_dependencies(),
        )

    def generate_values_yaml(self, environment: str = "dev") -> str:
        """Generate values.yaml for a given environment."""
        template = self.env.get_template("values.yaml.j2")
        profile = ENV_PROFILES.get(environment, ENV_PROFILES["dev"])
        engines = self._required_engines()
        return template.render(
            project_name=self.schema.project_name,
            environment=environment,
            profile=profile,
            engines=engines,
            StorageEngine=StorageEngine,
        )

    def generate_deployment_template(self) -> str:
        """Generate Helm templates/deployment.yaml."""
        template = self.env.get_template("deployment.yaml.j2")
        return template.render(project_name=self.schema.project_name)

    def generate_service_template(self) -> str:
        """Generate Helm templates/service.yaml."""
        template = self.env.get_template("service.yaml.j2")
        return template.render(project_name=self.schema.project_name)

    def generate_helpers_template(self) -> str:
        """Generate Helm templates/_helpers.tpl."""
        template = self.env.get_template("_helpers.tpl.j2")
        return template.render(project_name=self.schema.project_name)

    @staticmethod
    def _check_placeholder_credentials(files: dict[str, str]) -> list[str]:
        """Find any placeholder credentials ('changeme') in generated manifests.

        Returns a list of ``filename:line`` location strings.
        """
        locations: list[str] = []
        for filename, content in files.items():
            for match in _PLACEHOLDER_PATTERN.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                locations.append(f"{filename}:{line_num}")
        return locations

    @staticmethod
    def _check_latest_tag(files: dict[str, str]) -> list[str]:
        """Find any image references using the ``latest`` tag."""
        locations: list[str] = []
        for filename, content in files.items():
            for match in _LATEST_TAG_PATTERN.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                locations.append(f"{filename}:{line_num}")
        return locations

    def generate_all(self, *, allow_placeholder_creds: bool = False) -> dict[str, str]:
        """Generate a complete Helm chart as a dict of relative_path -> content.

        Args:
            allow_placeholder_creds: If ``True``, skip the hard error when placeholder
                credentials (``changeme``) are detected.  Intended only for local
                development.

        Raises:
            PlaceholderCredentialError: If placeholder credentials are detected and
                *allow_placeholder_creds* is ``False``.
        """
        chart_name = self.schema.project_name
        files: dict[str, str] = {}
        files[f"{chart_name}/Chart.yaml"] = self.generate_chart_yaml()
        files[f"{chart_name}/templates/deployment.yaml"] = self.generate_deployment_template()
        files[f"{chart_name}/templates/service.yaml"] = self.generate_service_template()
        files[f"{chart_name}/templates/_helpers.tpl"] = self.generate_helpers_template()

        for env_name in ENV_PROFILES:
            files[f"{chart_name}/values-{env_name}.yaml"] = self.generate_values_yaml(env_name)
        # Default values.yaml = dev
        files[f"{chart_name}/values.yaml"] = self.generate_values_yaml("dev")

        # Validate: placeholder credentials
        cred_locations = self._check_placeholder_credentials(files)
        if cred_locations:
            msg = (
                "Generated Helm values contain placeholder credentials ('changeme') "
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
                "Generated Helm chart references 'latest' image tag at: %s. "
                "Pin to a specific version for production use.",
                ", ".join(tag_locations),
            )

        return files

    def write_chart(
        self, output_dir: Path, *, allow_placeholder_creds: bool = False,
    ) -> list[Path]:
        """Write the full Helm chart to disk, return list of written paths."""
        written: list[Path] = []
        for rel_path, content in self.generate_all(
            allow_placeholder_creds=allow_placeholder_creds,
        ).items():
            full_path = output_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(full_path)
        return written
