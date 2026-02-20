"""Tests for ASD change detection (differ)."""

from __future__ import annotations

from ninja_codegen.differ import compute_diff, save_snapshot
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType


def test_first_sync_is_full(tmp_path, sample_schema):
    """First sync with no snapshot should report full sync."""
    snapshot_dir = tmp_path / ".ninjastack"
    snapshot_dir.mkdir()

    diff = compute_diff(sample_schema, snapshot_dir)

    assert diff.is_full_sync
    assert diff.has_changes
    assert len(diff.changed_entities) == 3
    assert len(diff.changed_domains) == 2
    assert diff.project_changed


def test_no_changes_after_snapshot(tmp_path, sample_schema):
    """After saving a snapshot, computing diff should show no changes."""
    snapshot_dir = tmp_path / ".ninjastack"
    snapshot_dir.mkdir()

    save_snapshot(sample_schema, snapshot_dir)
    diff = compute_diff(sample_schema, snapshot_dir)

    assert not diff.has_changes
    assert not diff.is_full_sync
    assert diff.changed_entities == []
    assert diff.changed_domains == []
    assert not diff.project_changed


def test_entity_change_detected(tmp_path, sample_schema):
    """Modifying an entity should be detected as a change."""
    snapshot_dir = tmp_path / ".ninjastack"
    snapshot_dir.mkdir()

    save_snapshot(sample_schema, snapshot_dir)

    # Modify the Order entity by adding a field
    modified_order = EntitySchema(
        name="Order",
        storage_engine="sql",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="customer_id", field_type=FieldType.UUID),
            FieldSchema(name="total", field_type=FieldType.FLOAT),
            FieldSchema(name="status", field_type=FieldType.STRING),
            FieldSchema(name="created_at", field_type=FieldType.DATETIME, nullable=True),
            FieldSchema(name="notes", field_type=FieldType.TEXT, nullable=True),
        ],
        description="A customer order",
    )

    modified_schema = sample_schema.model_copy(
        update={"entities": [modified_order, sample_schema.entities[1], sample_schema.entities[2]]}
    )

    diff = compute_diff(modified_schema, snapshot_dir)

    assert diff.has_changes
    assert "Order" in diff.changed_entities
    assert "Product" not in diff.changed_entities
    assert "Customer" not in diff.changed_entities


def test_domain_change_detected(tmp_path, sample_schema):
    """Modifying a domain should be detected."""
    snapshot_dir = tmp_path / ".ninjastack"
    snapshot_dir.mkdir()

    save_snapshot(sample_schema, snapshot_dir)

    # Add an entity to the Billing domain
    modified_domain = sample_schema.domains[0].model_copy(update={"entities": ["Order", "Customer", "Product"]})
    modified_schema = sample_schema.model_copy(update={"domains": [modified_domain, sample_schema.domains[1]]})

    diff = compute_diff(modified_schema, snapshot_dir)

    assert diff.has_changes
    assert "Billing" in diff.changed_domains
    assert "Inventory" not in diff.changed_domains


def test_removal_detected(tmp_path, sample_schema):
    """Removing an entity should be detected as a change."""
    snapshot_dir = tmp_path / ".ninjastack"
    snapshot_dir.mkdir()

    save_snapshot(sample_schema, snapshot_dir)

    # Remove the Customer entity
    modified_schema = sample_schema.model_copy(
        update={"entities": [sample_schema.entities[0], sample_schema.entities[1]]}
    )

    diff = compute_diff(modified_schema, snapshot_dir)

    assert diff.has_changes
    assert "Customer" in diff.changed_entities
