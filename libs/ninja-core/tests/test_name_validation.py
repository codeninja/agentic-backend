"""Tests for name validation — prevents SSTI, XSS, and YAML injection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import (
    EntitySchema,
    FieldSchema,
    FieldType,
    StorageEngine,
    validate_safe_name,
)
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import (
    Cardinality,
    RelationshipSchema,
    RelationshipType,
)


def _id_field() -> FieldSchema:
    return FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True)


class TestValidateSafeName:
    """Unit tests for the validate_safe_name helper."""

    def test_valid_simple_name(self):
        assert validate_safe_name("Order") == "Order"

    def test_valid_name_with_underscore(self):
        assert validate_safe_name("order_item") == "order_item"

    def test_valid_name_with_hyphen(self):
        assert validate_safe_name("my-project") == "my-project"

    def test_valid_name_with_space(self):
        assert validate_safe_name("My Project") == "My Project"

    def test_valid_name_starts_with_underscore(self):
        assert validate_safe_name("_internal") == "_internal"

    def test_rejects_jinja2_ssti_payload(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_safe_name("{{ 7*7 }}")

    def test_rejects_xss_script_tag(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_safe_name("<script>alert(1)</script>")

    def test_rejects_html_angle_brackets(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_safe_name("Order<br>")

    def test_rejects_yaml_delimiter(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_safe_name("name: value")

    def test_rejects_dot_notation(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_safe_name("module.name")

    def test_rejects_starts_with_digit(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_safe_name("123Entity")

    def test_rejects_too_long_name(self):
        with pytest.raises(ValueError, match="at most 128"):
            validate_safe_name("A" * 129)

    def test_accepts_max_length_name(self):
        name = "A" * 128
        assert validate_safe_name(name) == name


class TestFieldNameValidation:
    """Field names must be safe identifiers."""

    def test_rejects_ssti_field_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            FieldSchema(name="{{ config }}", field_type=FieldType.STRING)

    def test_rejects_xss_field_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            FieldSchema(name="<img onerror=alert(1)>", field_type=FieldType.STRING)


class TestEntityNameValidation:
    """Entity names must be safe identifiers."""

    def test_rejects_ssti_entity_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            EntitySchema(
                name="{{ 7*7 }}",
                storage_engine=StorageEngine.SQL,
                fields=[_id_field()],
            )

    def test_rejects_xss_entity_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            EntitySchema(
                name="<script>alert(1)</script>",
                storage_engine=StorageEngine.SQL,
                fields=[_id_field()],
            )

    def test_valid_entity_name_accepted(self):
        e = EntitySchema(
            name="OrderItem",
            storage_engine=StorageEngine.SQL,
            fields=[_id_field()],
        )
        assert e.name == "OrderItem"


class TestDomainNameValidation:
    """Domain names must be safe identifiers."""

    def test_rejects_ssti_domain_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            DomainSchema(name="{{ 7*7 }}", entities=["Order"])

    def test_valid_domain_name_accepted(self):
        d = DomainSchema(name="Billing", entities=["Order"])
        assert d.name == "Billing"


class TestRelationshipNameValidation:
    """Relationship names must be safe identifiers."""

    def test_rejects_ssti_relationship_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            RelationshipSchema(
                name="{{ exploit }}",
                source_entity="Order",
                target_entity="Customer",
                relationship_type=RelationshipType.SOFT,
                cardinality=Cardinality.ONE_TO_MANY,
            )

    def test_valid_relationship_name_accepted(self):
        r = RelationshipSchema(
            name="order_customer",
            source_entity="Order",
            target_entity="Customer",
            relationship_type=RelationshipType.SOFT,
            cardinality=Cardinality.ONE_TO_MANY,
        )
        assert r.name == "order_customer"


class TestProjectNameValidation:
    """Project names must be safe identifiers."""

    def test_rejects_ssti_project_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            AgenticSchema(project_name="{{ 7*7 }}")

    def test_rejects_yaml_injection_project_name(self):
        with pytest.raises(ValidationError, match="unsafe characters"):
            AgenticSchema(project_name="name: !!python/object")

    def test_valid_project_name_accepted(self):
        s = AgenticSchema(project_name="my-shop")
        assert s.project_name == "my-shop"
