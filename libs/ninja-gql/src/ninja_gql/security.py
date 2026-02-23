"""GraphQL security extensions — introspection control, depth & complexity limiting.

Provides Strawberry schema extensions that enforce configurable security
policies on incoming GraphQL operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from graphql import parse as gql_parse
from pydantic import BaseModel, Field
from strawberry.extensions import SchemaExtension

if TYPE_CHECKING:
    from strawberry.types import ExecutionContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class GraphQLSecurityConfig(BaseModel):
    """Security configuration for the generated GraphQL layer.

    Controls introspection visibility, query depth limits, and query
    complexity thresholds.
    """

    introspection_enabled: bool = Field(
        default=True,
        description="Allow introspection queries. Disable in production.",
    )
    max_query_depth: int = Field(
        default=10,
        ge=1,
        description="Maximum allowed nesting depth for queries.",
    )
    max_query_complexity: int = Field(
        default=1000,
        ge=1,
        description="Maximum total complexity cost for a single query.",
    )
    default_field_cost: int = Field(
        default=1,
        ge=0,
        description="Default cost assigned to each selected field.",
    )
    list_field_multiplier: int = Field(
        default=10,
        ge=1,
        description="Cost multiplier for fields that return lists.",
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Introspection control extension
# ---------------------------------------------------------------------------

_INTROSPECTION_FIELDS = frozenset({"__schema", "__type"})


class IntrospectionControlExtension(SchemaExtension):
    """Blocks introspection queries when disabled via configuration.

    Strawberry extension that inspects the raw query string for
    ``__schema`` or ``__type`` keywords and rejects the request when
    introspection is disabled.
    """

    def __init__(self, *, enabled: bool = True, **kwargs: Any) -> None:
        self._enabled = enabled
        super().__init__(**kwargs)

    def on_operation(self) -> Any:
        """Check for introspection fields before execution."""
        execution_context: ExecutionContext = self.execution_context
        if not self._enabled and execution_context.query:
            # Fast-path: check raw query string for introspection keywords
            if "__schema" in execution_context.query or "__type" in execution_context.query:
                logger.warning("Introspection query blocked by security policy")
                raise PermissionError("Introspection is disabled. Set NINJASTACK_ENV=development to enable.")
        yield


# ---------------------------------------------------------------------------
# Query depth validation extension
# ---------------------------------------------------------------------------


def _measure_depth(node: Any, current: int = 0) -> int:
    """Recursively measure the deepest selection depth in a parsed AST node.

    Parameters
    ----------
    node:
        A GraphQL AST node (typically a ``SelectionSetNode`` or
        ``FieldNode``).
    current:
        Current nesting depth.

    Returns
    -------
    int
        The maximum depth found.
    """
    selection_set = getattr(node, "selection_set", None)
    if selection_set is None or not selection_set.selections:
        return current

    max_child = current
    for selection in selection_set.selections:
        child_depth = _measure_depth(selection, current + 1)
        if child_depth > max_child:
            max_child = child_depth
    return max_child


class QueryDepthExtension(SchemaExtension):
    """Rejects queries that exceed a configurable nesting depth.

    Parses the raw query string and measures the deepest field selection
    chain.  If the depth exceeds ``max_depth``, the query is rejected
    before execution.
    """

    def __init__(self, *, max_depth: int = 10, **kwargs: Any) -> None:
        self._max_depth = max_depth
        super().__init__(**kwargs)

    def on_operation(self) -> Any:
        """Validate query depth before execution."""
        execution_context: ExecutionContext = self.execution_context
        query_str = execution_context.query
        if query_str:
            try:
                document = gql_parse(query_str)
            except Exception:
                yield
                return

            for definition in document.definitions:
                depth = _measure_depth(definition)
                if depth > self._max_depth:
                    logger.warning(
                        "Query depth %d exceeds limit %d",
                        depth,
                        self._max_depth,
                    )
                    raise PermissionError(f"Query depth {depth} exceeds maximum allowed depth of {self._max_depth}.")
        yield


# ---------------------------------------------------------------------------
# Query complexity analysis extension
# ---------------------------------------------------------------------------


def _measure_complexity(
    node: Any,
    default_cost: int = 1,
    list_multiplier: int = 10,
    multiplier: int = 1,
) -> int:
    """Calculate total complexity cost of a parsed AST node.

    Each field adds ``default_cost * multiplier`` to the total.  When a
    field has a sub-selection (i.e. returns an object or list), the cost
    of its children is multiplied by ``list_multiplier`` to approximate
    the fan-out of list fields.

    Parameters
    ----------
    node:
        A GraphQL AST node.
    default_cost:
        Base cost per field.
    list_multiplier:
        Multiplier applied to children of list-returning fields.
    multiplier:
        Inherited multiplier from parent context.

    Returns
    -------
    int
        Total estimated cost.
    """
    selection_set = getattr(node, "selection_set", None)
    if selection_set is None or not selection_set.selections:
        return 0

    total = 0
    for selection in selection_set.selections:
        field_cost = default_cost * multiplier
        total += field_cost

        child_ss = getattr(selection, "selection_set", None)
        if child_ss and child_ss.selections:
            # Nested object/list — apply list multiplier to children
            total += _measure_complexity(
                selection,
                default_cost=default_cost,
                list_multiplier=list_multiplier,
                multiplier=multiplier * list_multiplier,
            )

    return total


class QueryComplexityExtension(SchemaExtension):
    """Rejects queries whose estimated complexity exceeds a threshold.

    Uses a simple cost model: each field has a base cost, and nested
    selections multiply by a configurable list-field multiplier.
    """

    def __init__(
        self,
        *,
        max_complexity: int = 1000,
        default_field_cost: int = 1,
        list_field_multiplier: int = 10,
        **kwargs: Any,
    ) -> None:
        self._max_complexity = max_complexity
        self._default_field_cost = default_field_cost
        self._list_field_multiplier = list_field_multiplier
        super().__init__(**kwargs)

    def on_operation(self) -> Any:
        """Validate query complexity before execution."""
        execution_context: ExecutionContext = self.execution_context
        query_str = execution_context.query
        if query_str:
            try:
                document = gql_parse(query_str)
            except Exception:
                yield
                return

            for definition in document.definitions:
                cost = _measure_complexity(
                    definition,
                    default_cost=self._default_field_cost,
                    list_multiplier=self._list_field_multiplier,
                )
                if cost > self._max_complexity:
                    logger.warning(
                        "Query complexity %d exceeds limit %d",
                        cost,
                        self._max_complexity,
                    )
                    raise PermissionError(
                        f"Query complexity {cost} exceeds maximum allowed complexity of {self._max_complexity}."
                    )
        yield


# ---------------------------------------------------------------------------
# Helper: build extension list from config
# ---------------------------------------------------------------------------


def build_security_extensions(
    config: GraphQLSecurityConfig | None = None,
) -> list[type[SchemaExtension] | object]:
    """Build a list of Strawberry schema extensions from a security config.

    Returns extension *instances* wrapped in lambdas suitable for passing
    to ``strawberry.Schema(extensions=[...])``.
    """
    if config is None:
        config = GraphQLSecurityConfig()

    extensions: list[Any] = []

    # Introspection control — always add, toggle via config
    extensions.append(
        _make_extension_factory(
            IntrospectionControlExtension,
            enabled=config.introspection_enabled,
        )
    )

    # Query depth limiting
    extensions.append(
        _make_extension_factory(
            QueryDepthExtension,
            max_depth=config.max_query_depth,
        )
    )

    # Query complexity analysis
    extensions.append(
        _make_extension_factory(
            QueryComplexityExtension,
            max_complexity=config.max_query_complexity,
            default_field_cost=config.default_field_cost,
            list_field_multiplier=config.list_field_multiplier,
        )
    )

    return extensions


def _make_extension_factory(cls: type, **kwargs: Any) -> type:
    """Create a SchemaExtension subclass that passes kwargs on init.

    Strawberry expects extension classes (not instances) in the
    ``extensions`` list.  This factory creates a subclass whose
    ``__init__`` injects the provided kwargs.
    """

    class _Factory(cls):  # type: ignore[valid-type]
        def __init__(self, **init_kwargs: Any) -> None:
            merged = {**kwargs, **init_kwargs}
            super().__init__(**merged)

    _Factory.__name__ = f"{cls.__name__}Configured"
    _Factory.__qualname__ = _Factory.__name__
    return _Factory
