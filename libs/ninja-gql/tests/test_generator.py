"""Tests for the GQL generator."""

from __future__ import annotations

from ninja_core.schema.project import AgenticSchema
from ninja_gql.generator import GqlGenerator


class TestGqlGeneratorTypes:
    def test_generates_type_per_entity(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        types = gen.generate_types()

        assert set(types.keys()) == {"Customer", "Order", "Product"}

    def test_customer_type_has_fields(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        types = gen.generate_types()
        customer = types["Customer"]

        assert "id" in customer.__annotations__
        assert "name" in customer.__annotations__
        assert "email" in customer.__annotations__

    def test_order_type_has_fields(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        types = gen.generate_types()
        order = types["Order"]

        assert "customer_id" in order.__annotations__
        assert "total" in order.__annotations__
        assert "status" in order.__annotations__

    def test_relationship_field_attached(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        types = gen.generate_types()
        customer = types["Customer"]

        assert "customer_orders" in customer.__annotations__

    def test_nullable_field_type(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        types = gen.generate_types()
        product = types["Product"]

        # description is nullable
        assert "description" in product.__annotations__

    def test_types_are_strawberry_types(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        types = gen.generate_types()

        for t in types.values():
            assert hasattr(t, "__strawberry_definition__")

    def test_has_embeddable_fields(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)

        product = sample_asd.entities[2]
        customer = sample_asd.entities[0]

        assert gen.has_embeddable_fields(product) is True
        assert gen.has_embeddable_fields(customer) is False


class TestGqlGeneratorInputTypes:
    def test_generates_input_types(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        inputs = gen.generate_input_types()

        assert "Customer" in inputs
        create_cls, update_cls = inputs["Customer"]
        assert hasattr(create_cls, "__strawberry_definition__")
        assert hasattr(update_cls, "__strawberry_definition__")

    def test_create_input_pk_optional(self, sample_asd: AgenticSchema):
        gen = GqlGenerator(sample_asd)
        inputs = gen.generate_input_types()
        create_cls, _ = inputs["Customer"]

        # PK should be optional in create input
        assert create_cls.__annotations__["id"] is not None
