"""Tests for ASD serialization round-trip."""

from pathlib import Path

import pytest
from ninja_core.schema import (
    AgentConfig,
    AgenticSchema,
    Cardinality,
    DomainSchema,
    EmbeddingConfig,
    EntitySchema,
    FieldConstraint,
    FieldSchema,
    FieldType,
    ReasoningLevel,
    RelationshipSchema,
    RelationshipType,
    StorageEngine,
)
from ninja_core.serialization import load_schema, save_schema


def _build_full_schema() -> AgenticSchema:
    """Build a comprehensive ASD that exercises every model."""
    user = EntitySchema(
        name="User",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(
                name="email",
                field_type=FieldType.STRING,
                unique=True,
                constraints=FieldConstraint(max_length=255),
            ),
            FieldSchema(name="is_active", field_type=FieldType.BOOLEAN, default=True),
        ],
        description="Application user",
        tags=["auth"],
    )
    document = EntitySchema(
        name="Document",
        storage_engine=StorageEngine.VECTOR,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(
                name="content",
                field_type=FieldType.TEXT,
                embedding=EmbeddingConfig(
                    model="text-embedding-3-small",
                    dimensions=1536,
                    chunk_strategy="sentence",
                ),
            ),
        ],
    )
    person = EntitySchema(
        name="Person",
        storage_engine=StorageEngine.GRAPH,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
        ],
    )
    audit = EntitySchema(
        name="AuditLog",
        storage_engine=StorageEngine.MONGO,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="action", field_type=FieldType.STRING),
            FieldSchema(name="timestamp", field_type=FieldType.DATETIME),
        ],
        collection_name="audit_logs",
    )
    rel_hard = RelationshipSchema(
        name="user_documents",
        source_entity="User",
        target_entity="Document",
        relationship_type=RelationshipType.HARD,
        cardinality=Cardinality.ONE_TO_MANY,
        source_field="id",
        target_field="user_id",
    )
    rel_graph = RelationshipSchema(
        name="knows",
        source_entity="Person",
        target_entity="Person",
        relationship_type=RelationshipType.GRAPH,
        cardinality=Cardinality.MANY_TO_MANY,
        edge_label="KNOWS",
    )
    rel_soft = RelationshipSchema(
        name="similar_docs",
        source_entity="Document",
        target_entity="Document",
        relationship_type=RelationshipType.SOFT,
        cardinality=Cardinality.MANY_TO_MANY,
    )
    domain = DomainSchema(
        name="Knowledge",
        entities=["User", "Document", "Person"],
        agent_config=AgentConfig(
            model_provider="gemini",
            reasoning_level=ReasoningLevel.HIGH,
            tool_permissions=["search", "summarize"],
            temperature=0.3,
        ),
        description="Knowledge management domain",
    )
    return AgenticSchema(
        project_name="ninja-test",
        entities=[user, document, person, audit],
        relationships=[rel_hard, rel_graph, rel_soft],
        domains=[domain],
        description="Full integration test schema",
    )


class TestRoundTrip:
    def test_serialize_deserialize(self, tmp_path: Path):
        original = _build_full_schema()
        file_path = tmp_path / "schema.json"

        save_schema(original, file_path)
        loaded = load_schema(file_path)

        assert loaded == original

    def test_json_is_human_readable(self, tmp_path: Path):
        schema = AgenticSchema(project_name="minimal")
        file_path = tmp_path / "schema.json"
        save_schema(schema, file_path)

        text = file_path.read_text()
        assert "\n" in text  # Indented JSON
        assert '"project_name": "minimal"' in text

    def test_creates_parent_directories(self, tmp_path: Path):
        schema = AgenticSchema(project_name="test")
        nested = tmp_path / "a" / "b" / "schema.json"
        save_schema(schema, nested)
        assert nested.exists()

    def test_load_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_schema(tmp_path / "nope.json")

    def test_load_invalid_json_raises(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(Exception):
            load_schema(bad)

    def test_load_invalid_schema_raises(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"bogus": true}', encoding="utf-8")
        with pytest.raises(Exception):
            load_schema(bad)

    def test_all_storage_engines_round_trip(self, tmp_path: Path):
        original = _build_full_schema()
        engines = {e.storage_engine for e in original.entities}
        assert engines == {
            StorageEngine.SQL,
            StorageEngine.MONGO,
            StorageEngine.GRAPH,
            StorageEngine.VECTOR,
        }

        file_path = tmp_path / "schema.json"
        save_schema(original, file_path)
        loaded = load_schema(file_path)
        assert {e.storage_engine for e in loaded.entities} == engines

    def test_all_relationship_types_round_trip(self, tmp_path: Path):
        original = _build_full_schema()
        types = {r.relationship_type for r in original.relationships}
        assert types == {
            RelationshipType.HARD,
            RelationshipType.SOFT,
            RelationshipType.GRAPH,
        }

        file_path = tmp_path / "schema.json"
        save_schema(original, file_path)
        loaded = load_schema(file_path)
        assert {r.relationship_type for r in loaded.relationships} == types
