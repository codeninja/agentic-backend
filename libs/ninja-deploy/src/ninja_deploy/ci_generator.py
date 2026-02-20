"""GitHub Actions CI/CD workflow generator."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from ninja_core.schema.project import AgenticSchema


def _get_template_env() -> Environment:
    return Environment(
        loader=PackageLoader("ninja_deploy", "templates/github_actions"),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


class CIGenerator:
    """Generates GitHub Actions workflows from an ASD."""

    def __init__(
        self,
        schema: AgenticSchema,
        registry: str = "ghcr.io",
        apps: list[str] | None = None,
    ) -> None:
        self.schema = schema
        self.registry = registry
        self.apps = apps or ["ninja-api"]
        self.env = _get_template_env()

    def generate_deploy_workflow(self) -> str:
        """Generate the main deploy.yml GitHub Actions workflow."""
        template = self.env.get_template("deploy.yml.j2")
        return template.render(
            project_name=self.schema.project_name,
            registry=self.registry,
            apps=self.apps,
        )

    def generate_test_workflow(self) -> str:
        """Generate the test.yml GitHub Actions workflow."""
        template = self.env.get_template("test.yml.j2")
        return template.render(
            project_name=self.schema.project_name,
        )

    def generate_all(self) -> dict[str, str]:
        """Generate all CI/CD workflows. Returns dict of relative_path -> content."""
        return {
            "deploy.yml": self.generate_deploy_workflow(),
            "test.yml": self.generate_test_workflow(),
        }

    def write_workflows(self, output_dir: Path) -> list[Path]:
        """Write all workflows to disk, return list of written paths."""
        written: list[Path] = []
        for rel_path, content in self.generate_all().items():
            full_path = output_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(full_path)
        return written
