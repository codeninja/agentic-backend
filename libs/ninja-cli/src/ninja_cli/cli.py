"""Ninja CLI — Typer-based CLI for all Ninja Stack operations."""

from __future__ import annotations

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
) -> None:
    """Initialize a new Ninja Stack project with .ninjastack/ config."""
    if is_initialized(root):
        typer.echo(f".ninjastack/ already exists in {root.resolve()}. Skipping init.")
        raise typer.Exit(code=0)

    config = init_state(project_name, root)
    typer.echo(f"Initialized Ninja Stack project '{config.project_name}' in {root.resolve() / '.ninjastack'}")


@app.command()
def sync() -> None:
    """Sync ASD schema to generated code. (Not yet implemented)"""
    typer.echo("Not yet implemented")


@app.command()
def serve() -> None:
    """Start the Ninja Stack dev server. (Not yet implemented)"""
    typer.echo("Not yet implemented")


@app.command()
def deploy() -> None:
    """Deploy the Ninja Stack project. (Not yet implemented)"""
    typer.echo("Not yet implemented")


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
