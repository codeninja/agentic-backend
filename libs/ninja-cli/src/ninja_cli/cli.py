"""Ninja CLI — Typer-based CLI for all Ninja Stack operations."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import typer

from ninja_cli.state import init_state, is_initialized, load_config

app = typer.Typer(name="ninjastack", help="Ninja Stack CLI — schema-first agentic backend framework.")
create_app = typer.Typer(help="Scaffold new libs or apps.")
app.add_typer(create_app, name="create")


def _require_initialized(root: Path) -> None:
    """Exit with an error if the project is not initialized."""
    if not is_initialized(root):
        typer.echo(
            f"Project not initialized. Run 'ninjastack init' first. (checked {root.resolve()})",
            err=True,
        )
        raise typer.Exit(code=1)


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
def introspect(
    connection: list[str] = typer.Option(
        ...,
        "--connection",
        "-c",
        help="Database connection string (can be specified multiple times).",
    ),
    root: Path = typer.Option(Path("."), "--root", "-r", help="Project root directory."),
    save: bool = typer.Option(True, "--save/--no-save", help="Write discovered schema to .ninjastack/schema.json."),
) -> None:
    """Introspect one or more databases and build an ASD schema.

    Connects to each database, discovers entities and relationships,
    and merges the results into a single AgenticSchema.

    Examples:

        ninjastack introspect -c "postgresql://localhost/mydb"

        ninjastack introspect -c "postgresql://localhost/mydb" -c "mongodb://localhost/docs"
    """
    _require_initialized(root)

    import asyncio

    from ninja_core.serialization.io import save_schema
    from ninja_introspect.engine import IntrospectionEngine

    config = load_config(root)
    engine = IntrospectionEngine(project_name=config.project_name)

    typer.echo(f"Introspecting {len(connection)} connection(s)...")

    try:
        schema = asyncio.run(engine.run(connection))
    except ValueError as exc:
        typer.echo(f"Introspection failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"Introspection error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    entity_count = len(schema.entities)
    rel_count = len(schema.relationships)
    typer.echo(f"Discovered {entity_count} entities and {rel_count} relationships.")

    if save:
        schema_path = root / ".ninjastack" / "schema.json"
        save_schema(schema, schema_path)
        typer.echo(f"Schema saved to {schema_path}")
    else:
        typer.echo("Schema not saved (--no-save).")


@app.command()
def sync(
    root: Path = typer.Option(Path("."), "--root", "-r", help="Project root directory."),
    output_dir: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for generated code. Defaults to project root.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force full regeneration, ignoring change detection."),
) -> None:
    """Sync the ASD schema to generated code via ninja-codegen.

    Reads .ninjastack/schema.json, detects changes since the last sync,
    and generates Pydantic models, GraphQL types, agent definitions,
    and the FastAPI app shell.

    Examples:

        ninjastack sync

        ninjastack sync --force

        ninjastack sync --output ./generated
    """
    _require_initialized(root)

    from ninja_codegen.engine import sync as codegen_sync

    resolved_output = output_dir or root

    typer.echo("Syncing ASD schema to generated code...")

    try:
        result = codegen_sync(root=root, output_dir=resolved_output, force=force)
    except FileNotFoundError as exc:
        typer.echo(f"Sync failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"Sync error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.skipped:
        typer.echo("No changes detected. Schema is up to date.")
        return

    typer.echo(f"Generated {result.file_count} file(s):")
    for path in result.generated_files:
        typer.echo(f"  {path}")


@app.command()
def serve(
    root: Path = typer.Option(Path("."), "--root", "-r", help="Project root directory."),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind address."),
    port: int = typer.Option(8000, "--port", "-p", help="Port number."),
    reload: bool = typer.Option(True, "--reload/--no-reload", help="Enable auto-reload for development."),
) -> None:
    """Start the Ninja Stack FastAPI dev server.

    Launches a uvicorn dev server pointing at the generated FastAPI app.
    The app shell must have been generated first via 'ninjastack sync'.

    Examples:

        ninjastack serve

        ninjastack serve --host 0.0.0.0 --port 9000

        ninjastack serve --no-reload
    """
    _require_initialized(root)

    app_module = "_generated.app:app"
    app_path = root / "_generated" / "app.py"
    if not app_path.is_file():
        typer.echo(
            "Generated app not found. Run 'ninjastack sync' first to generate the app shell.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Starting dev server at http://{host}:{port} ...")

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        app_module,
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")

    try:
        result = subprocess.run(cmd, cwd=str(root))  # noqa: S603
        raise typer.Exit(code=result.returncode)
    except KeyboardInterrupt:
        typer.echo("\nServer stopped.")
    except FileNotFoundError:
        typer.echo(
            "uvicorn not found. Install it with: pip install uvicorn",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def deploy(
    root: Path = typer.Option(Path("."), "--root", "-r", help="Project root directory."),
    output_dir: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for manifests. Defaults to <root>/deploy/.",
    ),
    fmt: str = typer.Option(
        "k8s",
        "--format",
        help="Deployment format: k8s, helm, docker, or all.",
    ),
    app_name: str = typer.Option("ninja-api", "--app-name", help="Application name for manifests."),
    port: str = typer.Option("8000", "--port", "-p", help="Application port."),
) -> None:
    """Generate deployment manifests from the ASD schema.

    Reads .ninjastack/schema.json and generates Kubernetes manifests,
    Helm charts, Dockerfiles, or all of the above.

    Examples:

        ninjastack deploy

        ninjastack deploy --format helm --output ./charts

        ninjastack deploy --format all

        ninjastack deploy --format docker --app-name my-service --port 3000
    """
    _require_initialized(root)

    from ninja_core.serialization.io import load_schema

    schema_path = root / ".ninjastack" / "schema.json"
    try:
        schema = load_schema(schema_path)
    except FileNotFoundError:
        typer.echo(f"Schema not found at {schema_path}. Run 'ninjastack init' first.", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Failed to load schema: {exc}", err=True)
        raise typer.Exit(code=1)

    resolved_output = output_dir or (root / "deploy")
    valid_formats = ("k8s", "helm", "docker", "all")
    if fmt not in valid_formats:
        typer.echo(f"Invalid format '{fmt}'. Choose from: {', '.join(valid_formats)}", err=True)
        raise typer.Exit(code=1)

    all_written: list[Path] = []

    if fmt in ("k8s", "all"):
        from ninja_deploy.k8s_generator import K8sGenerator

        k8s_dir = resolved_output / "k8s"
        gen = K8sGenerator(schema)
        written = gen.write_manifests(k8s_dir)
        all_written.extend(written)
        typer.echo(f"K8s manifests: {len(written)} file(s) written to {k8s_dir}")

    if fmt in ("helm", "all"):
        from ninja_deploy.helm_generator import HelmGenerator

        helm_dir = resolved_output / "helm"
        gen = HelmGenerator(schema)
        written = gen.write_chart(helm_dir)
        all_written.extend(written)
        typer.echo(f"Helm chart: {len(written)} file(s) written to {helm_dir}")

    if fmt in ("docker", "all"):
        from ninja_deploy.docker_generator import DockerGenerator

        docker_dir = resolved_output / "docker"
        module = f"{app_name.replace('-', '_')}.main:app"
        apps_config = [{"name": app_name, "port": port, "module": module}]
        gen = DockerGenerator(schema, apps=apps_config)
        written = gen.write_dockerfiles(docker_dir)
        all_written.extend(written)
        typer.echo(f"Dockerfiles: {len(written)} file(s) written to {docker_dir}")

    typer.echo(f"\nTotal: {len(all_written)} deployment file(s) generated.")


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
