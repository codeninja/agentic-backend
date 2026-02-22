"""Tests for ASD schema validation — cross-entity integrity & single-model validators."""

import warnings

import pytest
from ninja_core.schema import (
    AgenticSchema,
    Cardinality,
    DomainSchema,
    EntitySchema,
    FieldConstraint,
    FieldSchema,
    FieldType,
    RelationshipSchema,
    RelationshipType,
    StorageEngine,
)
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pk_field(name: str = "id") -> FieldSchema:
    """Create a standard UUID primary key field."""
    return FieldSchema(name=name, field_type=FieldType.UUID, primary_key=True)


def _simple_entity(name: str, extra_fields: list[FieldSchema] | None = None) -> EntitySchema:
    """Create a minimal valid entity with a primary key."""
    fields = [_pk_field()]
    if extra_fields:
        fields.extend(extra_fields)
    return EntitySchema(
        name=name,
        storage_engine=StorageEngine.SQL,
        fields=fields,
    )


# ===========================================================================
# FieldConstraint validation
# ===========================================================================

class TestFieldConstraintValidation:
    def test_valid_constraints(self):
        c = FieldConstraint(min_length=0, max_length=255, ge=0, le=100)
        assert c.min_length == 0
        assert c.max_length == 255

    def test_min_length_equals_max_length(self):
        """Edge case: min == max is valid (exact length)."""
        c = FieldConstraint(min_length=10, max_length=10)
        assert c.min_length == c.max_length

    def test_ge_equals_le(self):
        """Edge case: ge == le is valid (exact value)."""
        c = FieldConstraint(ge=5.0, le=5.0)
        assert c.ge == c.le

    def test_min_length_exceeds_max_length_rejected(self):
        with pytest.raises(ValidationError, match="min_length.*cannot exceed.*max_length"):
            FieldConstraint(min_length=100, max_length=10)

    def test_ge_exceeds_le_rejected(self):
        with pytest.raises(ValidationError, match="ge.*cannot exceed.*le"):
            FieldConstraint(ge=50.0, le=10.0)

    def test_partial_constraints_no_conflict(self):
        """Only min_length set — no max to conflict with."""
        c = FieldConstraint(min_length=5)
        assert c.min_length == 5
        assert c.max_length is None

    # -------------------------------------------------------------------
    # Pattern validation — syntax
    # -------------------------------------------------------------------

    def test_valid_pattern_simple(self):
        """Simple regex patterns are accepted."""
        c = FieldConstraint(pattern=r"^[a-z]+$")
        assert c.pattern == r"^[a-z]+$"

    def test_valid_pattern_email_like(self):
        """Email-like pattern is accepted."""
        c = FieldConstraint(pattern=r"^[\w.+-]+@[\w-]+\.[\w.]+$")
        assert c.pattern is not None

    def test_valid_pattern_uuid(self):
        """UUID pattern is accepted."""
        c = FieldConstraint(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert c.pattern is not None

    def test_valid_pattern_fixed_repetition_in_group(self):
        """Fixed-width quantifier inside a quantified group is safe."""
        c = FieldConstraint(pattern=r"([a-z]{3})+")
        assert c.pattern is not None

    def test_invalid_pattern_syntax_rejected(self):
        """Malformed regex is rejected at model construction."""
        with pytest.raises(ValidationError, match="Invalid regex pattern"):
            FieldConstraint(pattern=r"[unclosed")

    def test_invalid_pattern_unbalanced_paren(self):
        with pytest.raises(ValidationError, match="Invalid regex pattern"):
            FieldConstraint(pattern=r"(abc")

    # -------------------------------------------------------------------
    # Pattern validation — ReDoS safety
    # -------------------------------------------------------------------

    def test_redos_nested_plus_plus(self):
        """(a+)+ is a classic ReDoS pattern — must be rejected."""
        with pytest.raises(ValidationError, match="nested quantifiers"):
            FieldConstraint(pattern=r"(a+)+$")

    def test_redos_nested_star_star(self):
        """(a*)* — must be rejected."""
        with pytest.raises(ValidationError, match="nested quantifiers"):
            FieldConstraint(pattern=r"(a*)*")

    def test_redos_nested_plus_star(self):
        """(a+)* — must be rejected."""
        with pytest.raises(ValidationError, match="nested quantifiers"):
            FieldConstraint(pattern=r"(a+)*")

    def test_redos_nested_star_plus(self):
        """(a*)+ — must be rejected."""
        with pytest.raises(ValidationError, match="nested quantifiers"):
            FieldConstraint(pattern=r"(a*)+")

    def test_redos_alternation_in_quantified_group(self):
        """(a|a)+ — ambiguous alternation inside quantifier."""
        with pytest.raises(ValidationError, match="nested quantifiers"):
            FieldConstraint(pattern=r"(a|a+)+")

    def test_redos_deeply_nested(self):
        """((a+)b)+ — inner quantifier inside quantified group."""
        with pytest.raises(ValidationError, match="nested quantifiers"):
            FieldConstraint(pattern=r"((a+)b)+")

    def test_redos_complex_evil_regex(self):
        """(([a-z])+.)+ — known evil pattern."""
        with pytest.raises(ValidationError, match="nested quantifiers"):
            FieldConstraint(pattern=r"(([a-z])+.)+")

    def test_safe_pattern_character_class_quantifier(self):
        """[a-z]+ is safe — no nesting."""
        c = FieldConstraint(pattern=r"[a-z]+")
        assert c.pattern is not None

    def test_safe_pattern_group_without_inner_quantifier(self):
        """(abc)+ is safe — group contents have no quantifier."""
        c = FieldConstraint(pattern=r"(abc)+")
        assert c.pattern is not None

    def test_safe_pattern_bounded_quantifier(self):
        """a{2,4} — bounded, no group."""
        c = FieldConstraint(pattern=r"a{2,4}")
        assert c.pattern is not None

    def test_none_pattern_accepted(self):
        """None pattern is fine (no constraint)."""
        c = FieldConstraint(pattern=None)
        assert c.pattern is None


# ===========================================================================
# FieldSchema validation
# ===========================================================================

class TestFieldSchemaValidation:
    def test_primary_key_nullable_rejected(self):
        with pytest.raises(ValidationError, match="must not be nullable"):
            FieldSchema(
                name="id", field_type=FieldType.UUID,
                primary_key=True, nullable=True,
            )

    def test_primary_key_non_nullable_ok(self):
        f = _pk_field()
        assert f.primary_key is True
        assert f.nullable is False

    def test_enum_without_enum_values_rejected(self):
        with pytest.raises(ValidationError, match="ENUM requires.*enum_values"):
            FieldSchema(name="status", field_type=FieldType.ENUM)

    def test_enum_with_empty_enum_values_rejected(self):
        with pytest.raises(ValidationError, match="ENUM requires.*enum_values"):
            FieldSchema(
                name="status", field_type=FieldType.ENUM,
                constraints=FieldConstraint(enum_values=[]),
            )

    def test_enum_with_enum_values_ok(self):
        f = FieldSchema(
            name="status", field_type=FieldType.ENUM,
            constraints=FieldConstraint(enum_values=["active", "inactive"]),
        )
        assert f.constraints.enum_values == ["active", "inactive"]

    def test_string_default_type_check(self):
        f = FieldSchema(name="title", field_type=FieldType.STRING, default="hello")
        assert f.default == "hello"

    def test_string_default_wrong_type_rejected(self):
        with pytest.raises(ValidationError, match="not compatible with field_type=string"):
            FieldSchema(name="title", field_type=FieldType.STRING, default=42)

    def test_integer_default_type_check(self):
        f = FieldSchema(name="count", field_type=FieldType.INTEGER, default=0)
        assert f.default == 0

    def test_integer_default_wrong_type_rejected(self):
        with pytest.raises(ValidationError, match="not compatible with field_type=integer"):
            FieldSchema(name="count", field_type=FieldType.INTEGER, default="hello")

    def test_float_default_accepts_int(self):
        """int is compatible with float fields."""
        f = FieldSchema(name="score", field_type=FieldType.FLOAT, default=5)
        assert f.default == 5

    def test_float_default_accepts_float(self):
        f = FieldSchema(name="score", field_type=FieldType.FLOAT, default=3.14)
        assert f.default == 3.14

    def test_float_default_wrong_type_rejected(self):
        with pytest.raises(ValidationError, match="not compatible with field_type=float"):
            FieldSchema(name="score", field_type=FieldType.FLOAT, default="nope")

    def test_boolean_default_type_check(self):
        f = FieldSchema(name="active", field_type=FieldType.BOOLEAN, default=True)
        assert f.default is True

    def test_boolean_default_wrong_type_rejected(self):
        with pytest.raises(ValidationError, match="not compatible with field_type=boolean"):
            FieldSchema(name="active", field_type=FieldType.BOOLEAN, default="yes")

    def test_none_default_always_ok(self):
        """None default is valid for any field type."""
        f = FieldSchema(name="x", field_type=FieldType.INTEGER, default=None)
        assert f.default is None

    def test_json_default_not_type_checked(self):
        """JSON/ARRAY/BINARY/DATETIME/DATE types are not strict-checked."""
        f = FieldSchema(name="meta", field_type=FieldType.JSON, default={"key": "val"})
        assert f.default == {"key": "val"}


# ===========================================================================
# EntitySchema validation
# ===========================================================================

class TestEntitySchemaValidation:
    def test_valid_entity(self):
        e = _simple_entity("User")
        assert e.name == "User"

    def test_duplicate_field_names_rejected(self):
        with pytest.raises(ValidationError, match="duplicate field name 'name'"):
            EntitySchema(
                name="Bad",
                storage_engine=StorageEngine.SQL,
                fields=[
                    _pk_field(),
                    FieldSchema(name="name", field_type=FieldType.STRING),
                    FieldSchema(name="name", field_type=FieldType.STRING),
                ],
            )

    def test_no_primary_key_rejected(self):
        with pytest.raises(ValidationError, match="must have exactly one primary key"):
            EntitySchema(
                name="NoPK",
                storage_engine=StorageEngine.SQL,
                fields=[FieldSchema(name="name", field_type=FieldType.STRING)],
            )

    def test_multiple_primary_keys_rejected(self):
        with pytest.raises(ValidationError, match="multiple primary key fields"):
            EntitySchema(
                name="DoublePK",
                storage_engine=StorageEngine.SQL,
                fields=[
                    FieldSchema(name="id1", field_type=FieldType.UUID, primary_key=True),
                    FieldSchema(name="id2", field_type=FieldType.UUID, primary_key=True),
                ],
            )

    def test_single_primary_key_ok(self):
        e = _simple_entity("Valid")
        pk_count = sum(1 for f in e.fields if f.primary_key)
        assert pk_count == 1


# ===========================================================================
# RelationshipSchema validation
# ===========================================================================

class TestRelationshipSchemaValidation:
    def test_hard_without_source_field_rejected(self):
        with pytest.raises(ValidationError, match="requires both source_field and target_field"):
            RelationshipSchema(
                name="bad_hard",
                source_entity="A",
                target_entity="B",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field=None,
                target_field="a_id",
            )

    def test_hard_without_target_field_rejected(self):
        with pytest.raises(ValidationError, match="requires both source_field and target_field"):
            RelationshipSchema(
                name="bad_hard",
                source_entity="A",
                target_entity="B",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id",
                target_field=None,
            )

    def test_hard_with_both_fields_ok(self):
        r = RelationshipSchema(
            name="valid_hard",
            source_entity="A",
            target_entity="B",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.ONE_TO_MANY,
            source_field="id",
            target_field="a_id",
        )
        assert r.source_field == "id"
        assert r.target_field == "a_id"

    def test_soft_without_fields_ok(self):
        r = RelationshipSchema(
            name="soft_link",
            source_entity="A",
            target_entity="B",
            relationship_type=RelationshipType.SOFT,
            cardinality=Cardinality.MANY_TO_MANY,
        )
        assert r.source_field is None

    def test_graph_without_edge_label_defaults_to_name(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = RelationshipSchema(
                name="knows",
                source_entity="A",
                target_entity="B",
                relationship_type=RelationshipType.GRAPH,
                cardinality=Cardinality.MANY_TO_MANY,
            )
            assert r.edge_label == "knows"
            assert len(w) == 1
            assert "no edge_label set" in str(w[0].message)

    def test_graph_with_edge_label_ok(self):
        r = RelationshipSchema(
            name="knows",
            source_entity="A",
            target_entity="B",
            relationship_type=RelationshipType.GRAPH,
            cardinality=Cardinality.MANY_TO_MANY,
            edge_label="KNOWS",
        )
        assert r.edge_label == "KNOWS"


# ===========================================================================
# AgenticSchema cross-entity validation
# ===========================================================================

class TestAgenticSchemaValidation:
    def test_empty_schema_valid(self):
        """Empty schemas (no entities/relationships/domains) should pass."""
        s = AgenticSchema(project_name="empty")
        assert s.entities == []

    def test_duplicate_entity_names_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate entity name 'User'"):
            AgenticSchema(
                project_name="dup",
                entities=[_simple_entity("User"), _simple_entity("User")],
            )

    def test_duplicate_relationship_names_rejected(self):
        user = _simple_entity("User")
        order = _simple_entity("Order", [
            FieldSchema(name="user_id", field_type=FieldType.UUID),
        ])
        rel = RelationshipSchema(
            name="link",
            source_entity="User",
            target_entity="Order",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.ONE_TO_MANY,
            source_field="id",
            target_field="user_id",
        )
        with pytest.raises(ValidationError, match="Duplicate relationship name 'link'"):
            AgenticSchema(
                project_name="dup",
                entities=[user, order],
                relationships=[rel, rel],
            )

    def test_duplicate_domain_names_rejected(self):
        user = _simple_entity("User")
        with pytest.raises(ValidationError, match="Duplicate domain name 'Core'"):
            AgenticSchema(
                project_name="dup",
                entities=[user],
                domains=[
                    DomainSchema(name="Core", entities=["User"]),
                    DomainSchema(name="Core", entities=["User"]),
                ],
            )

    def test_relationship_references_nonexistent_source(self):
        user = _simple_entity("User")
        rel = RelationshipSchema(
            name="bad",
            source_entity="Ghost",
            target_entity="User",
            relationship_type=RelationshipType.SOFT,
            cardinality=Cardinality.ONE_TO_MANY,
        )
        with pytest.raises(ValidationError, match="non-existent source entity 'Ghost'"):
            AgenticSchema(
                project_name="bad",
                entities=[user],
                relationships=[rel],
            )

    def test_relationship_references_nonexistent_target(self):
        user = _simple_entity("User")
        rel = RelationshipSchema(
            name="bad",
            source_entity="User",
            target_entity="Ghost",
            relationship_type=RelationshipType.SOFT,
            cardinality=Cardinality.ONE_TO_MANY,
        )
        with pytest.raises(ValidationError, match="non-existent target entity 'Ghost'"):
            AgenticSchema(
                project_name="bad",
                entities=[user],
                relationships=[rel],
            )

    def test_domain_references_nonexistent_entity(self):
        user = _simple_entity("User")
        with pytest.raises(ValidationError, match="non-existent entity 'Ghost'"):
            AgenticSchema(
                project_name="bad",
                entities=[user],
                domains=[DomainSchema(name="D", entities=["User", "Ghost"])],
            )

    def test_fk_field_not_on_source_entity_rejected(self):
        user = _simple_entity("User")
        order = _simple_entity("Order", [
            FieldSchema(name="user_id", field_type=FieldType.UUID),
        ])
        rel = RelationshipSchema(
            name="link",
            source_entity="User",
            target_entity="Order",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.ONE_TO_MANY,
            source_field="nonexistent_field",
            target_field="user_id",
        )
        with pytest.raises(ValidationError, match="source_field 'nonexistent_field'.*does not exist"):
            AgenticSchema(
                project_name="bad",
                entities=[user, order],
                relationships=[rel],
            )

    def test_fk_field_not_on_target_entity_rejected(self):
        user = _simple_entity("User")
        order = _simple_entity("Order")
        rel = RelationshipSchema(
            name="link",
            source_entity="User",
            target_entity="Order",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.ONE_TO_MANY,
            source_field="id",
            target_field="nonexistent_field",
        )
        with pytest.raises(ValidationError, match="target_field 'nonexistent_field'.*does not exist"):
            AgenticSchema(
                project_name="bad",
                entities=[user, order],
                relationships=[rel],
            )

    def test_valid_fk_fields_accepted(self):
        user = _simple_entity("User")
        order = _simple_entity("Order", [
            FieldSchema(name="user_id", field_type=FieldType.UUID),
        ])
        rel = RelationshipSchema(
            name="user_orders",
            source_entity="User",
            target_entity="Order",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.ONE_TO_MANY,
            source_field="id",
            target_field="user_id",
        )
        s = AgenticSchema(
            project_name="shop",
            entities=[user, order],
            relationships=[rel],
        )
        assert len(s.relationships) == 1

    def test_self_referential_relationship_allowed(self):
        """Employee → Employee for manager hierarchy is valid."""
        employee = _simple_entity("Employee", [
            FieldSchema(name="manager_id", field_type=FieldType.UUID, nullable=True),
        ])
        rel = RelationshipSchema(
            name="manager",
            source_entity="Employee",
            target_entity="Employee",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.MANY_TO_ONE,
            source_field="manager_id",
            target_field="id",
        )
        s = AgenticSchema(
            project_name="hr",
            entities=[employee],
            relationships=[rel],
        )
        assert len(s.relationships) == 1

    def test_entity_in_multiple_domains_allowed(self):
        """Entities can appear in multiple domains — shared entities."""
        user = _simple_entity("User")
        s = AgenticSchema(
            project_name="multi",
            entities=[user],
            domains=[
                DomainSchema(name="Auth", entities=["User"]),
                DomainSchema(name="Profile", entities=["User"]),
            ],
        )
        assert len(s.domains) == 2

    def test_orphan_entity_allowed(self):
        """Entities not in any domain are valid."""
        user = _simple_entity("User")
        s = AgenticSchema(
            project_name="orphan",
            entities=[user],
            domains=[],
        )
        assert len(s.entities) == 1

    def test_circular_hard_relationships_rejected(self):
        """A→B→C→A cycle in HARD relationships should be rejected."""
        a = _simple_entity("A", [FieldSchema(name="c_id", field_type=FieldType.UUID)])
        b = _simple_entity("B", [FieldSchema(name="a_id", field_type=FieldType.UUID)])
        c = _simple_entity("C", [FieldSchema(name="b_id", field_type=FieldType.UUID)])
        rels = [
            RelationshipSchema(
                name="a_to_b", source_entity="A", target_entity="B",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id", target_field="a_id",
            ),
            RelationshipSchema(
                name="b_to_c", source_entity="B", target_entity="C",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id", target_field="b_id",
            ),
            RelationshipSchema(
                name="c_to_a", source_entity="C", target_entity="A",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id", target_field="c_id",
            ),
        ]
        with pytest.raises(ValidationError, match="Circular dependency"):
            AgenticSchema(
                project_name="cycle",
                entities=[a, b, c],
                relationships=rels,
            )

    def test_circular_soft_relationships_allowed(self):
        """Cycles in SOFT relationships are fine — only HARD is checked."""
        a = _simple_entity("A")
        b = _simple_entity("B")
        rels = [
            RelationshipSchema(
                name="a_to_b", source_entity="A", target_entity="B",
                relationship_type=RelationshipType.SOFT,
                cardinality=Cardinality.ONE_TO_MANY,
            ),
            RelationshipSchema(
                name="b_to_a", source_entity="B", target_entity="A",
                relationship_type=RelationshipType.SOFT,
                cardinality=Cardinality.ONE_TO_MANY,
            ),
        ]
        s = AgenticSchema(
            project_name="soft_cycle",
            entities=[a, b],
            relationships=rels,
        )
        assert len(s.relationships) == 2

    def test_two_node_hard_cycle_rejected(self):
        """A→B→A in HARD relationships is a cycle."""
        a = _simple_entity("A", [FieldSchema(name="b_id", field_type=FieldType.UUID)])
        b = _simple_entity("B", [FieldSchema(name="a_id", field_type=FieldType.UUID)])
        rels = [
            RelationshipSchema(
                name="a_to_b", source_entity="A", target_entity="B",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_ONE,
                source_field="b_id", target_field="id",
            ),
            RelationshipSchema(
                name="b_to_a", source_entity="B", target_entity="A",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_ONE,
                source_field="a_id", target_field="id",
            ),
        ]
        with pytest.raises(ValidationError, match="Circular dependency"):
            AgenticSchema(
                project_name="cycle2",
                entities=[a, b],
                relationships=rels,
            )

    def test_linear_hard_chain_allowed(self):
        """A→B→C without cycle is valid."""
        a = _simple_entity("A")
        b = _simple_entity("B", [FieldSchema(name="a_id", field_type=FieldType.UUID)])
        c = _simple_entity("C", [FieldSchema(name="b_id", field_type=FieldType.UUID)])
        rels = [
            RelationshipSchema(
                name="a_to_b", source_entity="A", target_entity="B",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id", target_field="a_id",
            ),
            RelationshipSchema(
                name="b_to_c", source_entity="B", target_entity="C",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id", target_field="b_id",
            ),
        ]
        s = AgenticSchema(
            project_name="chain",
            entities=[a, b, c],
            relationships=rels,
        )
        assert len(s.relationships) == 2
