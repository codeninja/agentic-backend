"""Tests for the ASD → graph schema mapper."""

from __future__ import annotations

from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.project import AgenticSchema
from ninja_graph.mapper import GraphSchema, map_asd_to_graph_schema


def test_map_entities_to_node_labels(sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)

    assert len(schema.node_labels) == 3
    names = {nl.name for nl in schema.node_labels}
    assert names == {"User", "Post", "Comment"}


def test_node_label_properties(sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)
    user_label = next(nl for nl in schema.node_labels if nl.name == "User")

    assert user_label.primary_key == "id"
    assert set(user_label.properties) == {"id", "name", "email"}


def test_map_relationships_to_edge_types(sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)

    assert len(schema.edge_types) == 3


def test_edge_type_uses_edge_label_when_provided(sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)
    authored = next(et for et in schema.edge_types if et.source_label == "Post" and et.target_label == "User")

    # The relationship has edge_label="AUTHORED_BY" set explicitly
    assert authored.name == "AUTHORED_BY"


def test_edge_type_falls_back_to_name_upper(sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)
    has_comment = next(et for et in schema.edge_types if et.source_label == "Post" and et.target_label == "Comment")

    # No edge_label set, so falls back to name.upper()
    assert has_comment.name == "HAS_COMMENT"


def test_edge_type_properties(sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)
    authored = next(et for et in schema.edge_types if et.name == "AUTHORED_BY")

    assert "author_id" in authored.properties
    assert "id" in authored.properties


def test_empty_asd():
    asd = AgenticSchema(project_name="empty")
    schema = map_asd_to_graph_schema(asd)

    assert schema.node_labels == []
    assert schema.edge_types == []


def test_entity_without_primary_key():
    asd = AgenticSchema(
        project_name="no-pk",
        entities=[
            EntitySchema(
                name="Tag",
                storage_engine=StorageEngine.MONGO,
                fields=[
                    FieldSchema(name="name", field_type=FieldType.STRING),
                    FieldSchema(name="color", field_type=FieldType.STRING),
                ],
            ),
        ],
    )
    schema = map_asd_to_graph_schema(asd)

    assert len(schema.node_labels) == 1
    assert schema.node_labels[0].primary_key is None
    assert set(schema.node_labels[0].properties) == {"name", "color"}


def test_graph_schema_serialization(sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)
    data = schema.model_dump()

    restored = GraphSchema.model_validate(data)
    assert len(restored.node_labels) == len(schema.node_labels)
    assert len(restored.edge_types) == len(schema.edge_types)
