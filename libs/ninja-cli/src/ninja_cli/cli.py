"""Ninja CLI — Typer-based CLI for all Ninja Stack operations."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import typer

from ninja_cli.state import init_state, is_initialized

app = typer.Typer(name="ninjastack", help="Ninja Stack CLI — schema-first agentic backend framework.")
create_app = typer.Typer(help="Scaffold new libs or apps.")
app.add_typer(create_app, name="create")


@app.command()
def init(
    project_name: str = typer.Option("my-ninja-project", "--name", "-n", help="Project name."),
    root: Path = typer.Option(Path("."), "--root", "-r", help="Project root directory."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Launch the conversational setup assistant."),
) -> None:
    """Initialize a new Ninja Stack project with .ninjastack/ config."""
    if is_initialized(root):
        typer.echo(f".ninjastack/ already exists in {root.resolve()}. Skipping init.")
        raise typer.Exit(code=0)

    if interactive:
        import asyncio

        from ninja_setup_assistant.runner import run_assistant

        result = asyncio.run(run_assistant(project_name=project_name, root=root))
        if result is None:
            raise typer.Exit(code=1)
        typer.echo(f"Setup complete! Project '{project_name}' initialized with {len(result.entities)} entities.")
        return

    config = init_state(project_name, root)
    typer.echo(f"Initialized Ninja Stack project '{config.project_name}' in {root.resolve() / '.ninjastack'}")


@app.command()
def sync(
    root: Path = typer.Option(Path("."), "--root", "-r", help="Project root directory."),
    force: bool = typer.Option(False, "--force", "-f", help="Force full regeneration, skip change detection."),
) -> None:
    """Sync ASD schema to generated code."""
    if not is_initialized(root):
        typer.echo("Project not initialized. Run 'ninjastack init' first.", err=True)
        raise typer.Exit(code=1)

    from ninja_codegen.engine import sync as codegen_sync

    result = codegen_sync(root=root, force=force)
    if result.skipped:
        typer.echo("No changes detected — nothing to generate.")
        return
    for fpath in result.generated_files:
        typer.echo(f"  {fpath}")
    typer.echo(f"Synced {result.file_count} file(s).")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind address."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development."),
    schema_path: Path | None = typer.Option(None, "--schema-path", help="Override ASD schema path."),
) -> None:
    """Start the Ninja Stack dev server."""
    import uvicorn
    from ninja_api.app import create_app as create_ninja_app

    asd_path = schema_path or (_find_project_root() / ".ninjastack" / "schema.json")
    if not asd_path.exists():
        typer.echo(f"ASD schema not found at {asd_path}. Run 'ninjastack init' first.", err=True)
        raise typer.Exit(code=1)

    application = create_ninja_app(schema_path=asd_path)
    typer.echo(f"Starting Ninja Stack server on {host}:{port}")
    uvicorn.run(application, host=host, port=port, log_level="info")


@app.command()
def deploy(
    root: Path = typer.Option(Path("."), "--root", "-r", help="Project root directory."),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Output directory for K8s manifests."),
) -> None:
    """Generate Kubernetes deployment manifests from the ASD."""
    if not is_initialized(root):
        typer.echo("Project not initialized. Run 'ninjastack init' first.", err=True)
        raise typer.Exit(code=1)

    from ninja_core.serialization.io import load_schema
    from ninja_deploy.k8s_generator import K8sGenerator

    schema = load_schema(root / ".ninjastack" / "schema.json")
    generator = K8sGenerator(schema)
    dest = output_dir or root / "k8s"
    written = generator.write_manifests(dest)
    for fpath in written:
        typer.echo(f"  {fpath}")
    typer.echo(f"Wrote {len(written)} manifest(s) to {dest}.")


@app.command()
def introspect(
    connection_string: str = typer.Argument(help="Database connection URI (e.g. postgresql://host/db, sqlite:///path)."),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json or table."),
) -> None:
    """Introspect a database and print discovered schema entities and relationships."""
    if format not in ("json", "table"):
        typer.echo(f"Unknown format '{format}'. Use 'json' or 'table'.", err=True)
        raise typer.Exit(code=1)

    import asyncio
    import json as json_mod

    from ninja_introspect.engine import IntrospectionEngine

    engine = IntrospectionEngine(allow_private_hosts=True)

    try:
        schema = asyncio.run(engine.run([connection_string]))
    except Exception as exc:
        typer.echo(f"Introspection failed: {exc}", err=True)
        raise typer.Exit(code=1) from None

    if format == "json":
        typer.echo(json_mod.dumps(schema.model_dump(mode="json"), indent=2))
    else:
        # Table format
        typer.echo(f"Entities ({len(schema.entities)}):")
        for entity in schema.entities:
            fields = ", ".join(f.name for f in entity.fields)
            typer.echo(f"  {entity.name}  [{fields}]")
        if schema.relationships:
            typer.echo(f"\nRelationships ({len(schema.relationships)}):")
            for rel in schema.relationships:
                typer.echo(f"  {rel.source_entity} -> {rel.target_entity}  ({rel.relationship_type.value})")
        typer.echo(f"\nDiscovered {len(schema.entities)} entity(ies), {len(schema.relationships)} relationship(s).")


_VALID_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_MAX_NAME_LENGTH = 64


def _validate_name(name: str) -> str:
    """Validate a library or app name for safe use in shell commands.

    Names must start with a lowercase letter and contain only lowercase
    letters, digits, and hyphens.  Maximum length is 64 characters.

    Args:
        name: The candidate name to validate.

    Returns:
        The validated name (unchanged).

    Raises:
        typer.BadParameter: If the name is invalid.
    """
    if not name:
        raise typer.BadParameter("Name must not be empty.")
    if len(name) > _MAX_NAME_LENGTH:
        raise typer.BadParameter(f"Name must be at most {_MAX_NAME_LENGTH} characters.")
    if not _VALID_NAME_RE.match(name):
        raise typer.BadParameter(
            f"Invalid name '{name}'. "
            "Names must start with a lowercase letter and contain only lowercase letters, digits, and hyphens."
        )
    return name


def _find_project_root() -> Path:
    """Walk up to find the directory containing pyproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return current


@create_app.command("lib")
def create_lib(
    name: str = typer.Argument(help="Library name (e.g. ninja-persistence)."),
) -> None:
    """Scaffold a new library under libs/."""
    name = _validate_name(name)
    root = _find_project_root()
    script = root / "scripts" / "new_lib.sh"
    if not script.is_file():
        typer.echo(f"Scaffolding script not found: {script}", err=True)
        raise typer.Exit(code=1)
    result = subprocess.run([str(script), name], cwd=str(root), capture_output=True, text=True)  # noqa: S603
    typer.echo(result.stdout)
    if result.returncode != 0:
        typer.echo(result.stderr, err=True)
        raise typer.Exit(code=result.returncode)


@create_app.command("app")
def create_app_cmd(
    name: str = typer.Argument(help="App name (e.g. ninja-api)."),
) -> None:
    """Scaffold a new app under apps/."""
    name = _validate_name(name)
    root = _find_project_root()
    script = root / "scripts" / "new_app.sh"
    if not script.is_file():
        typer.echo(f"Scaffolding script not found: {script}", err=True)
        raise typer.Exit(code=1)
    result = subprocess.run([str(script), name], cwd=str(root), capture_output=True, text=True)  # noqa: S603
    typer.echo(result.stdout)
    if result.returncode != 0:
        typer.echo(result.stderr, err=True)
        raise typer.Exit(code=result.returncode)


if __name__ == "__main__":
    app()
