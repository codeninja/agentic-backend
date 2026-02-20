"""Tests for the embedding strategy."""

from ninja_core.schema.entity import (
    EmbeddingConfig,
    EntitySchema,
    FieldSchema,
    FieldType,
    StorageEngine,
)
from ninja_persistence.embedding.strategy import EmbeddingStrategy


def _entity_with_embedding() -> EntitySchema:
    return EntitySchema(
        name="Article",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="title", field_type=FieldType.STRING),
            FieldSchema(
                name="body",
                field_type=FieldType.TEXT,
                embedding=EmbeddingConfig(model="text-embedding-3-small", dimensions=1536),
            ),
            FieldSchema(name="views", field_type=FieldType.INTEGER),
        ],
    )


def _entity_without_embedding() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="bio", field_type=FieldType.TEXT),
            FieldSchema(name="age", field_type=FieldType.INTEGER),
        ],
    )


def test_get_embeddable_fields():
    strategy = EmbeddingStrategy()
    entity = _entity_with_embedding()
    fields = strategy.get_embeddable_fields(entity)
    assert len(fields) == 1
    assert fields[0].name == "body"


def test_get_embeddable_fields_none():
    strategy = EmbeddingStrategy()
    entity = _entity_without_embedding()
    fields = strategy.get_embeddable_fields(entity)
    assert len(fields) == 0


def test_build_text_with_embedding_config():
    strategy = EmbeddingStrategy()
    entity = _entity_with_embedding()
    record = {"id": "1", "title": "Hello", "body": "World content here", "views": 100}
    text = strategy.build_text_for_embedding(entity, record)
    assert text == "World content here"


def test_build_text_fallback_to_string_fields():
    strategy = EmbeddingStrategy()
    entity = _entity_without_embedding()
    record = {"id": "1", "name": "Alice", "bio": "Developer", "age": 30}
    text = strategy.build_text_for_embedding(entity, record)
    # Should concatenate name (STRING) and bio (TEXT)
    assert "Alice" in text
    assert "Developer" in text


def test_build_text_empty_record():
    strategy = EmbeddingStrategy()
    entity = _entity_without_embedding()
    text = strategy.build_text_for_embedding(entity, {})
    assert text == ""


def test_get_model_for_field_with_config():
    strategy = EmbeddingStrategy()
    entity = _entity_with_embedding()
    field = entity.fields[2]  # body field with embedding config
    assert strategy.get_model_for_field(field) == "text-embedding-3-small"


def test_get_model_for_field_without_config():
    strategy = EmbeddingStrategy(model_name="custom-model")
    entity = _entity_without_embedding()
    field = entity.fields[1]  # name field, no embedding
    assert strategy.get_model_for_field(field) == "custom-model"


def test_get_dimensions_for_field_with_config():
    strategy = EmbeddingStrategy()
    entity = _entity_with_embedding()
    field = entity.fields[2]
    assert strategy.get_dimensions_for_field(field) == 1536


def test_get_dimensions_for_field_without_config():
    strategy = EmbeddingStrategy(dimensions=768)
    entity = _entity_without_embedding()
    field = entity.fields[1]
    assert strategy.get_dimensions_for_field(field) == 768


def test_custom_separator():
    strategy = EmbeddingStrategy(separator=" | ")
    entity = _entity_without_embedding()
    record = {"id": "1", "name": "Alice", "bio": "Developer", "age": 30}
    text = strategy.build_text_for_embedding(entity, record)
    assert " | " in text
