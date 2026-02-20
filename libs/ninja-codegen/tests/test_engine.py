"""Tests for the sync engine (full pipeline)."""

from __future__ import annotations

import json
from pathlib import Path

from ninja_codegen.engine import sync_schema
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType
from ninja_core.schema.project import AgenticSchema


def _setup_project(tmp_path: Path, schema: AgenticSchema) -> Path:
    """Set up a minimal project structure with .ninjastack/."""
    ninjastack = tmp_path / ".ninjastack"
    ninjastack.mkdir()
    schema_path = ninjastack / "schema.json"
    schema_path.write_text(json.dumps(schema.model_dump(mode="json"), indent=2))
    return tmp_path


def test_full_sync(tmp_path, sample_schema):
    """Full sync generates all expected files."""
    root = _setup_project(tmp_path, sample_schema)

    result = sync_schema(sample_schema, root=root, output_dir=root)

    assert not result.skipped
    assert result.file_count > 0
    assert result.diff is not None
    assert result.diff.is_full_sync

    # Check generated structure
    gen = root / "_generated"
    assert (gen / "models" / "order.py").exists()
    assert (gen / "models" / "product.py").exists()
    assert (gen / "models" / "customer.py").exists()
    assert (gen / "agents" / "order_agent.py").exists()
    assert (gen / "agents" / "billing_agent.py").exists()
    assert (gen / "agents" / "inventory_agent.py").exists()
    assert (gen / "graphql" / "order_gql.py").exists()
    assert (gen / "app" / "main.py").exists()


def test_sync_idempotent(tmp_path, sample_schema):
    """Running sync twice produces no changes on the second run."""
    root = _setup_project(tmp_path, sample_schema)

    result1 = sync_schema(sample_schema, root=root, output_dir=root)
    assert not result1.skipped

    # Collect file contents after first sync
    gen = root / "_generated"
    files_after_first: dict[str, str] = {}
    for f in gen.rglob("*.py"):
        files_after_first[str(f.relative_to(gen))] = f.read_text()

    # Second sync should be skipped (no changes)
    result2 = sync_schema(sample_schema, root=root, output_dir=root)
    assert result2.skipped

    # Force sync and verify content is identical
    result3 = sync_schema(sample_schema, root=root, output_dir=root, force=True)
    assert not result3.skipped

    for f in gen.rglob("*.py"):
        key = str(f.relative_to(gen))
        assert f.read_text() == files_after_first[key], f"Content mismatch in {key}"


def test_incremental_sync(tmp_path, sample_schema):
    """Incremental sync only regenerates changed entities."""
    root = _setup_project(tmp_path, sample_schema)

    # First full sync
    sync_schema(sample_schema, root=root, output_dir=root)

    # Modify just the Order entity
    modified_order = EntitySchema(
        name="Order",
        storage_engine="sql",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="customer_id", field_type=FieldType.UUID),
            FieldSchema(name="total", field_type=FieldType.FLOAT),
            FieldSchema(name="status", field_type=FieldType.STRING),
            FieldSchema(name="notes", field_type=FieldType.TEXT, nullable=True),
        ],
        description="A customer order",
    )

    modified_schema = sample_schema.model_copy(
        update={"entities": [modified_order, sample_schema.entities[1], sample_schema.entities[2]]}
    )

    result = sync_schema(modified_schema, root=root, output_dir=root)

    assert not result.skipped
    assert result.diff is not None
    assert "Order" in result.diff.changed_entities
    assert not result.diff.is_full_sync


def test_force_sync(tmp_path, sample_schema):
    """Force sync regenerates everything regardless of changes."""
    root = _setup_project(tmp_path, sample_schema)

    # First sync to create snapshot
    sync_schema(sample_schema, root=root, output_dir=root)

    # Force sync should not skip
    result = sync_schema(sample_schema, root=root, output_dir=root, force=True)

    assert not result.skipped
    assert result.file_count > 0


def test_sync_creates_snapshot(tmp_path, sample_schema):
    """Sync should create a snapshot file after generation."""
    root = _setup_project(tmp_path, sample_schema)

    sync_schema(sample_schema, root=root, output_dir=root)

    snapshot = root / ".ninjastack" / ".codegen_snapshot.json"
    assert snapshot.exists()

    data = json.loads(snapshot.read_text())
    assert "entity:Order" in data
    assert "entity:Product" in data
    assert "domain:Billing" in data
    assert "project:meta" in data


def test_generated_models_have_header(tmp_path, sample_schema):
    """All generated files should have the codegen header."""
    root = _setup_project(tmp_path, sample_schema)
    sync_schema(sample_schema, root=root, output_dir=root)

    gen = root / "_generated"
    for f in gen.rglob("*.py"):
        content = f.read_text()
        assert "AUTO-GENERATED" in content, f"Missing header in {f}"
