"""ninja-gql — GraphQL layer generator for Ninja Stack."""

from ninja_gql.generator import GqlGenerator
from ninja_gql.schema import build_schema

__all__ = ["GqlGenerator", "build_schema"]
