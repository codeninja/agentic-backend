"""ASD-driven Dockerfile generator."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from ninja_core.schema.project import AgenticSchema


def _get_template_env() -> Environment:
    return Environment(
        loader=PackageLoader("ninja_deploy", "templates/docker"),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


# Default apps in the NinjaStack monorepo
DEFAULT_APPS: list[dict[str, str]] = [
    {"name": "ninja-api", "port": "8000", "module": "ninja_api.main:app"},
]


class DockerGenerator:
    """Generates Dockerfiles from an ASD."""

    def __init__(self, schema: AgenticSchema, apps: list[dict[str, str]] | None = None) -> None:
        self.schema = schema
        self.apps = apps or DEFAULT_APPS
        self.env = _get_template_env()

    def generate_dockerfile(self, app_name: str, port: str = "8000", module: str = "main:app") -> str:
        """Generate a Dockerfile for a given app."""
        template = self.env.get_template("Dockerfile.j2")
        return template.render(
            project_name=self.schema.project_name,
            app_name=app_name,
            port=port,
            module=module,
        )

    def generate_dockerignore(self) -> str:
        """Generate a .dockerignore file."""
        template = self.env.get_template("dockerignore.j2")
        return template.render()

    def generate_all(self) -> dict[str, str]:
        """Generate Dockerfiles for all apps. Returns dict of relative_path -> content."""
        files: dict[str, str] = {}
        for app in self.apps:
            files[f"{app['name']}/Dockerfile"] = self.generate_dockerfile(
                app_name=app["name"],
                port=app.get("port", "8000"),
                module=app.get("module", "main:app"),
            )
        files[".dockerignore"] = self.generate_dockerignore()
        return files

    def write_dockerfiles(self, output_dir: Path) -> list[Path]:
        """Write all Dockerfiles to disk, return list of written paths."""
        written: list[Path] = []
        for rel_path, content in self.generate_all().items():
            full_path = output_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(full_path)
        return written
