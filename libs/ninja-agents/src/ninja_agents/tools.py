"""Tool generation helpers — given an EntitySchema, produce CRUD tool definitions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from ninja_core.schema.entity import EntitySchema

from ninja_agents.tracing import AgentSpan


@dataclass(frozen=True)
class ToolDefinition:
    """A generated tool that an agent can invoke."""

    name: str
    description: str
    entity_name: str
    operation: str
    handler: Callable[..., Any]


def _make_handler(entity_name: str, operation: str) -> Callable[..., Any]:
    """Create a stub handler for a CRUD operation.

    In a full system, these delegate to the persistence layer.
    The stub returns a dict describing what would be executed.
    """

    def handler(**kwargs: Any) -> dict[str, Any]:
        return {
            "entity": entity_name,
            "operation": operation,
            "params": kwargs,
        }

    handler.__name__ = f"{entity_name.lower()}_{operation}"
    handler.__doc__ = f"{operation} operation for {entity_name}"
    return handler


_CRUD_OPERATIONS: list[tuple[str, str]] = [
    ("get", "Retrieve a single {entity} by ID"),
    ("list", "List {entity} records with optional filters"),
    ("create", "Create a new {entity} record"),
    ("update", "Update an existing {entity} record"),
    ("delete", "Delete a {entity} record by ID"),
    ("search_semantic", "Semantic search across {entity} records"),
]


def generate_crud_tools(entity: EntitySchema) -> list[ToolDefinition]:
    """Generate CRUD + semantic search tool definitions for an entity."""
    tools: list[ToolDefinition] = []
    for operation, desc_template in _CRUD_OPERATIONS:
        name = f"{entity.name.lower()}_{operation}"
        description = desc_template.format(entity=entity.name)
        handler = _make_handler(entity.name, operation)
        tools.append(
            ToolDefinition(
                name=name,
                description=description,
                entity_name=entity.name,
                operation=operation,
                handler=handler,
            )
        )
    return tools


def invoke_tool(tool: ToolDefinition, span: AgentSpan | None = None, **kwargs: Any) -> Any:
    """Invoke a tool, optionally recording the call in a trace span."""
    start = time.monotonic()
    error: str | None = None
    success = True
    try:
        result = tool.handler(**kwargs)
    except Exception as exc:
        error = str(exc)
        success = False
        raise
    else:
        return result
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        if span is not None:
            span.record_tool_call(
                tool_name=tool.name,
                input_summary=str(kwargs)[:200],
                output_summary="" if not success else str(result)[:200],  # type: ignore[possibly-undefined]
                duration_ms=duration_ms,
                success=success,
                error=error,
            )
