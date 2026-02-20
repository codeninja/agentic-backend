"""Sync engine — orchestrates the full code generation pipeline.

Reads the ASD from .ninjastack/schema.json, detects changes via the differ,
runs the appropriate generators, and writes output into the project tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ninja_core.schema.project import AgenticSchema
from ninja_core.serialization.io import load_schema

from .differ import ASDDiff, compute_diff, save_snapshot
from .generators.agents import generate_agents
from .generators.apps import generate_app_shell
from .generators.graphql import generate_graphql
from .generators.models import generate_models


@dataclass
class SyncResult:
    """Result of a sync operation."""

    generated_files: list[Path] = field(default_factory=list)
    diff: ASDDiff | None = None
    skipped: bool = False

    @property
    def file_count(self) -> int:
        return len(self.generated_files)


def sync(
    root: Path | None = None,
    output_dir: Path | None = None,
    force: bool = False,
) -> SyncResult:
    """Run the full sync pipeline.

    Args:
        root: Project root containing .ninjastack/. Defaults to cwd.
        output_dir: Where to write generated code. Defaults to root.
        force: If True, skip change detection and regenerate everything.

    Returns:
        SyncResult with list of generated files and diff info.
    """
    root = root or Path(".")
    output_dir = output_dir or root

    schema = load_schema(root / ".ninjastack" / "schema.json")
    return sync_schema(schema, root=root, output_dir=output_dir, force=force)


def sync_schema(
    schema: AgenticSchema,
    root: Path | None = None,
    output_dir: Path | None = None,
    force: bool = False,
) -> SyncResult:
    """Run the sync pipeline from an in-memory AgenticSchema.

    Args:
        schema: The ASD to generate from.
        root: Project root for snapshot storage. Defaults to cwd.
        output_dir: Where to write generated code. Defaults to root.
        force: If True, skip change detection and regenerate everything.

    Returns:
        SyncResult with list of generated files and diff info.
    """
    root = root or Path(".")
    output_dir = output_dir or root
    snapshot_dir = root / ".ninjastack"

    # Change detection
    diff = compute_diff(schema, snapshot_dir)

    if not force and not diff.has_changes:
        return SyncResult(skipped=True, diff=diff)

    generated: list[Path] = []

    # Determine what to generate
    if force or diff.is_full_sync:
        entities_to_gen = schema.entities
        domains_to_gen = schema.domains
    else:
        entity_names = set(diff.changed_entities)
        domain_names = set(diff.changed_domains)
        entities_to_gen = [e for e in schema.entities if e.name in entity_names]
        domains_to_gen = [d for d in schema.domains if d.name in domain_names]

    # Run generators
    if entities_to_gen:
        generated.extend(generate_models(entities_to_gen, output_dir))
        generated.extend(generate_graphql(entities_to_gen, output_dir))

    if entities_to_gen or domains_to_gen:
        generated.extend(generate_agents(entities_to_gen, domains_to_gen, output_dir))

    if diff.project_changed or diff.is_full_sync or force:
        app_path = generate_app_shell(schema.project_name, output_dir)
        generated.append(app_path)

    # Save snapshot after successful generation
    save_snapshot(schema, snapshot_dir)

    return SyncResult(generated_files=generated, diff=diff)
