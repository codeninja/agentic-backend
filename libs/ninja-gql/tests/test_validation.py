"""Tests for JSON scalar input validation against ASD entity definitions."""

from __future__ import annotations

import pytest
from ninja_core.schema.entity import (
    EntitySchema,
    FieldConstraint,
    FieldSchema,
    FieldType,
    StorageEngine,
)
from ninja_core.schema.project import AgenticSchema
from ninja_gql.validation import (
    InputValidationError,
    validate_create_input,
    validate_update_input,
)


@pytest.fixture()
def customer_entity() -> EntitySchema:
    """Entity with various field types and constraints."""
    return EntitySchema(
        name="Customer",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(
                name="name",
                field_type=FieldType.STRING,
                constraints=FieldConstraint(min_length=1, max_length=100),
            ),
            FieldSchema(name="email", field_type=FieldType.STRING),
            FieldSchema(name="age", field_type=FieldType.INTEGER, nullable=True),
            FieldSchema(
                name="score",
                field_type=FieldType.FLOAT,
                nullable=True,
                constraints=FieldConstraint(ge=0.0, le=100.0),
            ),
            FieldSchema(name="active", field_type=FieldType.BOOLEAN, nullable=True),
        ],
        description="A customer with various field types.",
    )


@pytest.fixture()
def enum_entity() -> EntitySchema:
    """Entity with an enum field."""
    return EntitySchema(
        name="Task",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="title", field_type=FieldType.STRING),
            FieldSchema(
                name="status",
                field_type=FieldType.ENUM,
                constraints=FieldConstraint(enum_values=["open", "closed", "pending"]),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Create input validation
# ---------------------------------------------------------------------------


class TestValidateCreateInput:
    """Tests for create mutation input validation."""

    def test_valid_input_passes(self, customer_entity: EntitySchema):
        result = validate_create_input(
            customer_entity,
            {"name": "Alice", "email": "alice@test.com"},
        )
        assert result["name"] == "Alice"
        assert result["email"] == "alice@test.com"

    def test_unknown_field_rejected(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "Alice", "email": "a@b.c", "secret_admin": True},
            )
        assert "Unknown fields" in str(exc_info.value)
        assert "secret_admin" in str(exc_info.value)

    def test_multiple_unknown_fields_rejected(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "A", "email": "a@b.c", "foo": 1, "bar": 2},
            )
        assert "Unknown fields" in str(exc_info.value)

    def test_required_field_missing(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(customer_entity, {"name": "Alice"})
        assert "Required field 'email' is missing" in str(exc_info.value)

    def test_type_mismatch_string_field(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": 123, "email": "a@b.c"},
            )
        assert "expected string" in str(exc_info.value)

    def test_type_mismatch_integer_field(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "Alice", "email": "a@b.c", "age": "not-an-int"},
            )
        assert "expected integer" in str(exc_info.value)

    def test_type_mismatch_float_field(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "Alice", "email": "a@b.c", "score": "high"},
            )
        assert "expected number" in str(exc_info.value)

    def test_type_mismatch_boolean_field(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "Alice", "email": "a@b.c", "active": "yes"},
            )
        assert "expected boolean" in str(exc_info.value)

    def test_boolean_not_confused_with_int(self, customer_entity: EntitySchema):
        """Booleans should not pass as integers."""
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "Alice", "email": "a@b.c", "age": True},
            )
        assert "expected integer" in str(exc_info.value)

    def test_string_max_length_constraint(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "A" * 101, "email": "a@b.c"},
            )
        assert "exceeds maximum" in str(exc_info.value)

    def test_string_min_length_constraint(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "", "email": "a@b.c"},
            )
        assert "below minimum" in str(exc_info.value)

    def test_numeric_ge_constraint(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "Alice", "email": "a@b.c", "score": -1.0},
            )
        assert "below minimum" in str(exc_info.value)

    def test_numeric_le_constraint(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                customer_entity,
                {"name": "Alice", "email": "a@b.c", "score": 101.0},
            )
        assert "exceeds maximum" in str(exc_info.value)

    def test_nullable_field_accepts_none(self, customer_entity: EntitySchema):
        result = validate_create_input(
            customer_entity,
            {"name": "Alice", "email": "a@b.c", "age": None},
        )
        assert result["age"] is None

    def test_nullable_field_can_be_omitted(self, customer_entity: EntitySchema):
        result = validate_create_input(
            customer_entity,
            {"name": "Alice", "email": "a@b.c"},
        )
        assert "age" not in result

    def test_enum_valid_value(self, enum_entity: EntitySchema):
        result = validate_create_input(
            enum_entity,
            {"title": "Fix bug", "status": "open"},
        )
        assert result["status"] == "open"

    def test_enum_invalid_value(self, enum_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(
                enum_entity,
                {"title": "Fix bug", "status": "invalid"},
            )
        assert "not one of the allowed values" in str(exc_info.value)

    def test_non_dict_input_rejected(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_create_input(customer_entity, "not a dict")  # type: ignore
        assert "JSON object" in str(exc_info.value)

    def test_integer_accepted_for_float_field(self, customer_entity: EntitySchema):
        """Integer values should be accepted for float fields."""
        result = validate_create_input(
            customer_entity,
            {"name": "Alice", "email": "a@b.c", "score": 50},
        )
        assert result["score"] == 50

    def test_primary_key_in_input_allowed(self, customer_entity: EntitySchema):
        """Primary key in create input is allowed (may be user-supplied)."""
        result = validate_create_input(
            customer_entity,
            {"id": "custom-id", "name": "Alice", "email": "a@b.c"},
        )
        assert result["id"] == "custom-id"


# ---------------------------------------------------------------------------
# Update input validation
# ---------------------------------------------------------------------------


class TestValidateUpdateInput:
    """Tests for update mutation patch validation."""

    def test_valid_patch_passes(self, customer_entity: EntitySchema):
        result = validate_update_input(
            customer_entity,
            {"name": "Bob"},
        )
        assert result["name"] == "Bob"

    def test_unknown_field_rejected(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_update_input(
                customer_entity,
                {"name": "Bob", "is_admin": True},
            )
        assert "Unknown fields" in str(exc_info.value)

    def test_primary_key_modification_rejected(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_update_input(
                customer_entity,
                {"id": "new-id", "name": "Bob"},
            )
        assert "Cannot modify primary key" in str(exc_info.value)

    def test_all_fields_optional_in_patch(self, customer_entity: EntitySchema):
        """Patch can update just one field without requiring others."""
        result = validate_update_input(
            customer_entity,
            {"email": "new@test.com"},
        )
        assert result["email"] == "new@test.com"

    def test_empty_patch_passes(self, customer_entity: EntitySchema):
        result = validate_update_input(customer_entity, {})
        assert result == {}

    def test_type_mismatch_in_patch(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_update_input(
                customer_entity,
                {"age": "not-a-number"},
            )
        assert "expected integer" in str(exc_info.value)

    def test_constraint_violation_in_patch(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_update_input(
                customer_entity,
                {"name": "A" * 101},
            )
        assert "exceeds maximum" in str(exc_info.value)

    def test_non_dict_patch_rejected(self, customer_entity: EntitySchema):
        with pytest.raises(InputValidationError) as exc_info:
            validate_update_input(customer_entity, [1, 2, 3])  # type: ignore
        assert "JSON object" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Integration: validation in resolvers
# ---------------------------------------------------------------------------


class TestResolverValidationIntegration:
    """Tests that validation errors surface as GraphQL errors."""

    @pytest.fixture(autouse=True)
    def _auth_context(self):
        from ninja_auth.agent_context import clear_user_context, set_user_context
        from ninja_auth.context import UserContext

        ctx = UserContext(user_id="test", permissions=["write:*", "delete:*"], provider="test")
        token = set_user_context(ctx)
        yield
        clear_user_context(token)

    async def test_create_unknown_field_returns_graphql_error(self, sample_asd: AgenticSchema):
        """Unknown fields in create mutation produce a GraphQL error."""
        from ninja_gql.schema import build_schema

        class MockRepo:
            async def find_by_id(self, id):
                return None

            async def find_many(self, filters=None, limit=100):
                return []

            async def create(self, data):
                return {**data, "id": "new-id"}

            async def update(self, id, patch):
                return None

            async def delete(self, id):
                return True

            async def search_semantic(self, query, limit=10):
                return []

            async def upsert_embedding(self, id, embedding):
                pass

        repos = {"Customer": MockRepo(), "Order": MockRepo(), "Product": MockRepo()}
        schema = build_schema(sample_asd, repo_getter=lambda name: repos[name])

        result = await schema.execute(
            'mutation { createCustomer(input: {name: "Alice", email: "a@b.c", is_admin: true}) { id } }'
        )
        assert result.errors is not None
        assert any("Unknown fields" in str(e) for e in result.errors)

    async def test_create_valid_input_succeeds(self, sample_asd: AgenticSchema):
        """Valid create input passes through validation."""
        from ninja_gql.schema import build_schema

        class MockRepo:
            async def find_by_id(self, id):
                return None

            async def find_many(self, filters=None, limit=100):
                return []

            async def create(self, data):
                return {**data, "id": "new-id"}

            async def update(self, id, patch):
                return None

            async def delete(self, id):
                return True

            async def search_semantic(self, query, limit=10):
                return []

            async def upsert_embedding(self, id, embedding):
                pass

        repos = {"Customer": MockRepo(), "Order": MockRepo(), "Product": MockRepo()}
        schema = build_schema(sample_asd, repo_getter=lambda name: repos[name])

        result = await schema.execute('mutation { createCustomer(input: {name: "Alice", email: "a@b.c"}) { id name } }')
        assert result.errors is None
        assert result.data["createCustomer"]["name"] == "Alice"
