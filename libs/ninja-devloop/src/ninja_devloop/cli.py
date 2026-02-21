"""CLI entry point for ninja-board commands."""

from __future__ import annotations

import json
import logging
import sys

import typer

from ninja_devloop.board_controller import BoardController
from ninja_devloop.models import BoardStatus

app = typer.Typer(name="ninja-board", no_args_is_help=True)

# Default cache location — relative to project root
_DEFAULT_CACHE = ".dev-loop-board-cache.json"


def _setup_logging(verbose: bool = True) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [board] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger = logging.getLogger("ninja-board")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO if verbose else logging.WARNING)


def _get_controller(cache_path: str | None = None) -> BoardController:
    path = cache_path or _DEFAULT_CACHE
    return BoardController(cache_path=path)


@app.command()
def sync(cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path")) -> None:
    """Full sync from GitHub — fetches all board items and enriches with issue details."""
    _setup_logging()
    ctrl = _get_controller(cache_path)
    state = ctrl.full_sync()
    summary = state.status_summary()
    total = sum(summary.values())
    typer.echo(f"Synced {total} items")
    for status_name, count in sorted(summary.items()):
        typer.echo(f"  {status_name}: {count}")


@app.command("issues-by-status")
def issues_by_status(
    status: str = typer.Argument(..., help="Board status name (e.g., 'Triage', 'Todo')"),
    cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path"),
) -> None:
    """List issue numbers with the given status (from cache)."""
    ctrl = _get_controller(cache_path)
    try:
        board_status = BoardStatus(status)
    except ValueError:
        typer.echo(f"Unknown status: {status}", err=True)
        raise typer.Exit(1)
    items = ctrl.get_state().by_status(board_status)
    for item in items:
        typer.echo(str(item.issue_number))


@app.command("count-status")
def count_status(
    status: str = typer.Argument(..., help="Board status name"),
    cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path"),
) -> None:
    """Count items with the given status (from cache)."""
    ctrl = _get_controller(cache_path)
    try:
        board_status = BoardStatus(status)
    except ValueError:
        typer.echo(f"Unknown status: {status}", err=True)
        raise typer.Exit(1)
    count = len(ctrl.get_state().by_status(board_status))
    typer.echo(str(count))


@app.command("set-status")
def set_status_cmd(
    issue_number: int = typer.Argument(..., help="Issue number"),
    status: str = typer.Argument(..., help="Target status name (e.g., 'Todo', 'AI Review')"),
    cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path"),
) -> None:
    """Transition an issue to a new status (write-through: updates GitHub + cache)."""
    _setup_logging()
    ctrl = _get_controller(cache_path)
    try:
        board_status = BoardStatus(status)
    except ValueError:
        typer.echo(f"Unknown status: {status}", err=True)
        raise typer.Exit(1)
    try:
        ctrl.set_status(issue_number, board_status)
        typer.echo(f"#{issue_number} → {status}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def context(
    issue_number: int = typer.Argument(..., help="Issue number"),
    cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path"),
) -> None:
    """Output full JSON context for an issue (for agent prompt injection)."""
    ctrl = _get_controller(cache_path)
    try:
        ctx = ctrl.get_issue_context(issue_number)
        typer.echo(json.dumps(ctx, indent=2))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def summary(
    cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path"),
) -> None:
    """Print board status summary (from cache)."""
    ctrl = _get_controller(cache_path)
    state = ctrl.get_state()
    counts = state.status_summary()
    if not counts:
        typer.echo("No items in board cache")
        return
    # Display in canonical order
    order = [
        "Triage",
        "Planning",
        "Todo",
        "In Progress",
        "AI Review",
        "Rejected",
        "In Review",
        "Done",
        "Need Human",
    ]
    for name in order:
        c = counts.get(name, 0)
        if c > 0:
            typer.echo(f"{name}: {c}")


@app.command("prioritized-todo")
def prioritized_todo(
    cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path"),
) -> None:
    """List todo issues sorted by priority (from cache)."""
    ctrl = _get_controller(cache_path)
    items = ctrl.get_state().prioritized_todo()
    for item in items:
        typer.echo(str(item.issue_number))


@app.command("needs-sync")
def needs_sync(
    cache_path: str = typer.Option(_DEFAULT_CACHE, "--cache", help="Cache file path"),
) -> None:
    """Check if sync interval has elapsed. Exit 0 if sync needed, exit 1 if not."""
    ctrl = _get_controller(cache_path)
    if ctrl.needs_sync():
        raise typer.Exit(0)
    else:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
