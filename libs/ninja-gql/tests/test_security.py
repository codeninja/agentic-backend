"""Tests for GraphQL security extensions — introspection, depth, complexity."""

from __future__ import annotations

import pytest
from graphql import parse as gql_parse
from ninja_core.schema.project import AgenticSchema
from ninja_gql.schema import build_schema
from ninja_gql.security import (
    GraphQLSecurityConfig,
    _measure_complexity,
    _measure_depth,
    build_security_extensions,
)

# ---------------------------------------------------------------------------
# Introspection control
# ---------------------------------------------------------------------------


class TestIntrospectionControl:
    """Tests for the IntrospectionControlExtension."""

    async def test_introspection_enabled_by_default(self, sample_asd: AgenticSchema):
        """Introspection works with default config (enabled)."""
        schema = build_schema(sample_asd)
        result = await schema.execute("{ __schema { types { name } } }")
        assert result.errors is None
        assert result.data is not None
        assert "__schema" in result.data

    async def test_introspection_disabled_blocks_schema_query(self, sample_asd: AgenticSchema):
        """Introspection __schema is blocked when disabled."""
        config = GraphQLSecurityConfig(introspection_enabled=False)
        schema = build_schema(sample_asd, security_config=config)
        result = await schema.execute("{ __schema { types { name } } }")
        assert result.errors is not None
        assert any("Introspection is disabled" in str(e) for e in result.errors)

    async def test_introspection_disabled_blocks_type_query(self, sample_asd: AgenticSchema):
        """Introspection __type is blocked when disabled."""
        config = GraphQLSecurityConfig(introspection_enabled=False)
        schema = build_schema(sample_asd, security_config=config)
        result = await schema.execute('{ __type(name: "Query") { fields { name } } }')
        assert result.errors is not None
        assert any("Introspection is disabled" in str(e) for e in result.errors)

    async def test_introspection_enabled_explicit(self, sample_asd: AgenticSchema):
        """Introspection works when explicitly enabled."""
        config = GraphQLSecurityConfig(introspection_enabled=True)
        schema = build_schema(sample_asd, security_config=config)
        result = await schema.execute("{ __schema { queryType { name } } }")
        assert result.errors is None

    async def test_normal_queries_work_when_introspection_disabled(self, sample_asd: AgenticSchema):
        """Non-introspection queries are not affected."""
        config = GraphQLSecurityConfig(introspection_enabled=False)
        schema = build_schema(sample_asd, security_config=config)
        # This should fail for missing repo, not introspection
        result = await schema.execute('{ getCustomer(id: "test") { id } }')
        assert result.errors is not None
        assert not any("Introspection" in str(e) for e in result.errors)


# ---------------------------------------------------------------------------
# Query depth limiting
# ---------------------------------------------------------------------------


class TestQueryDepthLimiting:
    """Tests for the QueryDepthExtension."""

    async def test_shallow_query_passes(self, sample_asd: AgenticSchema):
        """A simple shallow query passes depth validation."""
        config = GraphQLSecurityConfig(max_query_depth=5)
        schema = build_schema(sample_asd, security_config=config)
        result = await schema.execute('{ getCustomer(id: "test") { id name } }')
        # Should fail due to no repo, not depth
        assert result.errors is not None
        assert not any("depth" in str(e).lower() for e in result.errors)

    async def test_query_at_depth_limit_passes(self, sample_asd: AgenticSchema):
        """A query exactly at the depth limit passes."""
        config = GraphQLSecurityConfig(max_query_depth=3)
        schema = build_schema(sample_asd, security_config=config)
        # Depth 2: query -> getCustomer -> { id name }
        result = await schema.execute('{ getCustomer(id: "test") { id name } }')
        assert not any("depth" in str(e).lower() for e in (result.errors or []))

    async def test_deeply_nested_query_rejected(self, sample_asd: AgenticSchema):
        """A deeply nested query exceeding the limit is rejected."""
        # Set depth limit to 1 — even a simple field selection exceeds it
        config = GraphQLSecurityConfig(max_query_depth=1)
        schema = build_schema(sample_asd, security_config=config)
        # This query has depth 2: query -> getCustomer -> { id name }
        result = await schema.execute('{ getCustomer(id: "test") { id name } }')
        assert result.errors is not None
        assert any("depth" in str(e).lower() for e in result.errors)

    def test_measure_depth_flat_query(self):
        """_measure_depth correctly measures a flat query."""
        doc = gql_parse("{ getUser { id name } }")
        depth = _measure_depth(doc.definitions[0])
        assert depth == 2  # query -> getUser -> fields

    def test_measure_depth_nested_query(self):
        """_measure_depth correctly measures nested fields."""
        doc = gql_parse("{ getUser { profile { address { city } } } }")
        depth = _measure_depth(doc.definitions[0])
        assert depth == 4  # query -> getUser -> profile -> address -> city

    async def test_default_depth_limit_is_10(self, sample_asd: AgenticSchema):
        """Default depth limit should be 10."""
        config = GraphQLSecurityConfig()
        assert config.max_query_depth == 10


# ---------------------------------------------------------------------------
# Query complexity limiting
# ---------------------------------------------------------------------------


class TestQueryComplexityLimiting:
    """Tests for the QueryComplexityExtension."""

    async def test_simple_query_passes(self, sample_asd: AgenticSchema):
        """A simple query is within the default complexity limit."""
        config = GraphQLSecurityConfig(max_query_complexity=100)
        schema = build_schema(sample_asd, security_config=config)
        result = await schema.execute('{ getCustomer(id: "test") { id name } }')
        # Should fail for repo reasons, not complexity
        assert not any("complexity" in str(e).lower() for e in (result.errors or []))

    async def test_very_low_complexity_limit_rejects(self, sample_asd: AgenticSchema):
        """An extremely low complexity limit rejects even simple queries."""
        config = GraphQLSecurityConfig(max_query_complexity=1, default_field_cost=5)
        schema = build_schema(sample_asd, security_config=config)
        result = await schema.execute('{ getCustomer(id: "test") { id name email } }')
        assert result.errors is not None
        assert any("complexity" in str(e).lower() for e in result.errors)

    def test_measure_complexity_simple(self):
        """_measure_complexity correctly calculates for a flat query."""
        doc = gql_parse("{ getUser { id name email } }")
        cost = _measure_complexity(doc.definitions[0], default_cost=1, list_multiplier=10)
        # query level: 1 field (getUser) = 1
        # nested: 3 fields at multiplier 10 = 30
        assert cost == 1 + 30

    def test_measure_complexity_nested(self):
        """_measure_complexity correctly handles nested objects."""
        doc = gql_parse("{ getUser { profile { name } } }")
        cost = _measure_complexity(doc.definitions[0], default_cost=1, list_multiplier=10)
        # query level: 1 field (getUser) = 1
        # level 2: 1 field (profile) = 10
        # level 3: 1 field (name) = 100
        assert cost == 1 + 10 + 100

    async def test_default_complexity_limit(self):
        """Default complexity limit should be 1000."""
        config = GraphQLSecurityConfig()
        assert config.max_query_complexity == 1000

    async def test_list_multiplier_increases_cost(self):
        """List fields should cost more than scalar fields."""
        config = GraphQLSecurityConfig()
        assert config.list_field_multiplier == 10


# ---------------------------------------------------------------------------
# Security config model
# ---------------------------------------------------------------------------


class TestGraphQLSecurityConfig:
    """Tests for the GraphQLSecurityConfig Pydantic model."""

    def test_defaults(self):
        config = GraphQLSecurityConfig()
        assert config.introspection_enabled is True
        assert config.max_query_depth == 10
        assert config.max_query_complexity == 1000
        assert config.default_field_cost == 1
        assert config.list_field_multiplier == 10

    def test_custom_values(self):
        config = GraphQLSecurityConfig(
            introspection_enabled=False,
            max_query_depth=5,
            max_query_complexity=500,
            default_field_cost=2,
            list_field_multiplier=5,
        )
        assert config.introspection_enabled is False
        assert config.max_query_depth == 5
        assert config.max_query_complexity == 500

    def test_min_depth_validation(self):
        with pytest.raises(Exception):
            GraphQLSecurityConfig(max_query_depth=0)

    def test_min_complexity_validation(self):
        with pytest.raises(Exception):
            GraphQLSecurityConfig(max_query_complexity=0)


# ---------------------------------------------------------------------------
# Extension builder
# ---------------------------------------------------------------------------


class TestBuildSecurityExtensions:
    """Tests for the build_security_extensions helper."""

    def test_returns_three_extensions(self):
        extensions = build_security_extensions()
        assert len(extensions) == 3

    def test_custom_config_applies(self):
        config = GraphQLSecurityConfig(max_query_depth=3)
        extensions = build_security_extensions(config)
        assert len(extensions) == 3

    def test_none_config_uses_defaults(self):
        extensions = build_security_extensions(None)
        assert len(extensions) == 3
