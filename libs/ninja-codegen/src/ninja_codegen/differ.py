"""ASD change detection via hash-based diffing.

Compares the current ASD against a stored snapshot to determine
which entities, domains, and relationships have changed, enabling
incremental code generation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ninja_core.schema.project import AgenticSchema

SNAPSHOT_FILENAME = ".codegen_snapshot.json"


@dataclass(frozen=True)
class ASDDiff:
    """Result of comparing current ASD against a previous snapshot."""

    changed_entities: list[str] = field(default_factory=list)
    changed_domains: list[str] = field(default_factory=list)
    project_changed: bool = False
    is_full_sync: bool = False

    @property
    def has_changes(self) -> bool:
        return self.is_full_sync or self.project_changed or bool(self.changed_entities) or bool(self.changed_domains)


def _hash_dict(data: dict) -> str:
    """Produce a stable hash for a dictionary by serializing with sorted keys."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_hashes(schema: AgenticSchema) -> dict[str, str]:
    """Build a map of component name -> hash for every entity and domain."""
    hashes: dict[str, str] = {}
    for entity in schema.entities:
        hashes[f"entity:{entity.name}"] = _hash_dict(entity.model_dump(mode="json"))
    for domain in schema.domains:
        hashes[f"domain:{domain.name}"] = _hash_dict(domain.model_dump(mode="json"))
    hashes["project:meta"] = _hash_dict(
        {
            "version": schema.version,
            "project_name": schema.project_name,
            "description": schema.description,
            "relationships": [r.model_dump(mode="json") for r in schema.relationships],
        }
    )
    return hashes


def compute_diff(schema: AgenticSchema, snapshot_dir: Path) -> ASDDiff:
    """Compare the current ASD against the stored snapshot.

    Args:
        schema: The current ASD.
        snapshot_dir: Directory where the snapshot file is stored.

    Returns:
        ASDDiff describing what changed.
    """
    snapshot_path = snapshot_dir / SNAPSHOT_FILENAME
    current_hashes = _build_hashes(schema)

    if not snapshot_path.exists():
        return ASDDiff(
            changed_entities=[e.name for e in schema.entities],
            changed_domains=[d.name for d in schema.domains],
            project_changed=True,
            is_full_sync=True,
        )

    stored: dict[str, str] = json.loads(snapshot_path.read_text())

    changed_entities: list[str] = []
    changed_domains: list[str] = []
    project_changed = False

    for key, current_hash in current_hashes.items():
        if stored.get(key) != current_hash:
            prefix, name = key.split(":", 1)
            if prefix == "entity":
                changed_entities.append(name)
            elif prefix == "domain":
                changed_domains.append(name)
            elif prefix == "project":
                project_changed = True

    # Detect removals (keys in stored but not in current)
    for key in stored:
        if key not in current_hashes:
            prefix, name = key.split(":", 1)
            if prefix == "entity" and name not in changed_entities:
                changed_entities.append(name)
            elif prefix == "domain" and name not in changed_domains:
                changed_domains.append(name)

    return ASDDiff(
        changed_entities=changed_entities,
        changed_domains=changed_domains,
        project_changed=project_changed,
    )


def save_snapshot(schema: AgenticSchema, snapshot_dir: Path) -> None:
    """Persist the current ASD hashes as the new snapshot."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / SNAPSHOT_FILENAME
    hashes = _build_hashes(schema)
    snapshot_path.write_text(json.dumps(hashes, indent=2))
