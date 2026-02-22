"""Tool generation helpers — given an EntitySchema, produce plain-function CRUD tools.

ADK auto-generates tool schemas from function name + docstring + type hints,
so each tool is a simple callable (no wrapper dataclass needed).
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ninja_core.schema.entity import EntitySchema

from ninja_agents.tracing import AgentSpan

# Import lazily to avoid circular dependency at module level.
_sanitize_error: Callable[..., str] | None = None


def _get_sanitize_error() -> Callable[..., str]:
    """Lazy import of sanitize_error to avoid circular imports."""
    global _sanitize_error
    if _sanitize_error is None:
        from ninja_agents.safety import sanitize_error

        _sanitize_error = sanitize_error
    return _sanitize_error


def _make_tool(entity_name: str, operation: str, description: str) -> Callable[..., Any]:
    """Create a plain-function tool for a CRUD operation.

    In a full system, these delegate to the persistence layer.
    The stub returns a dict describing what would be executed.
    """

    def tool(**kwargs: Any) -> dict[str, Any]:
        return {
            "entity": entity_name,
            "operation": operation,
            "params": kwargs,
        }

    tool.__name__ = f"{entity_name.lower()}_{operation}"
    tool.__qualname__ = tool.__name__
    tool.__doc__ = description
    return tool


_CRUD_OPERATIONS: list[tuple[str, str]] = [
    ("get", "Retrieve a single {entity} by ID."),
    ("list", "List {entity} records with optional filters."),
    ("create", "Create a new {entity} record."),
    ("update", "Update an existing {entity} record."),
    ("delete", "Delete a {entity} record by ID."),
    ("search_semantic", "Semantic search across {entity} records."),
]


def generate_crud_tools(entity: EntitySchema) -> list[Callable[..., Any]]:
    """Generate CRUD + semantic search tool functions for an entity.

    Each returned function has ``__name__`` set to ``<entity>_<operation>``
    and a docstring describing the operation — this is all ADK needs to
    build the tool schema automatically.
    """
    tools: list[Callable[..., Any]] = []
    for operation, desc_template in _CRUD_OPERATIONS:
        description = desc_template.format(entity=entity.name)
        tools.append(_make_tool(entity.name, operation, description))
    return tools


def invoke_tool(
    tool: Callable[..., Any],
    span: AgentSpan | None = None,
    **kwargs: Any,
) -> Any:
    """Invoke a tool function, optionally recording the call in a trace span."""
    start = time.monotonic()
    error: str | None = None
    success = True
    try:
        result = tool(**kwargs)
    except Exception as exc:
        error = _get_sanitize_error()(exc)
        success = False
        raise
    else:
        return result
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        if span is not None:
            span.record_tool_call(
                tool_name=getattr(tool, "__name__", "unknown"),
                input_summary=str(kwargs)[:200],
                output_summary="" if not success else str(result)[:200],  # type: ignore[possibly-undefined]
                duration_ms=duration_ms,
                success=success,
                error=error,
            )
