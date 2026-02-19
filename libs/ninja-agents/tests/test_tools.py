"""Tests for tool generation from EntitySchema."""

from ninja_agents.tools import generate_crud_tools, invoke_tool
from ninja_agents.tracing import AgentSpan
from ninja_core.schema.entity import EntitySchema


class TestGenerateCrudTools:
    def test_generates_six_tools(self, order_entity: EntitySchema) -> None:
        tools = generate_crud_tools(order_entity)
        assert len(tools) == 6

    def test_tool_names_prefixed_with_entity(self, order_entity: EntitySchema) -> None:
        tools = generate_crud_tools(order_entity)
        names = [t.name for t in tools]
        assert "order_get" in names
        assert "order_list" in names
        assert "order_create" in names
        assert "order_update" in names
        assert "order_delete" in names
        assert "order_search_semantic" in names

    def test_all_tools_reference_correct_entity(self, order_entity: EntitySchema) -> None:
        tools = generate_crud_tools(order_entity)
        for tool in tools:
            assert tool.entity_name == "Order"

    def test_tool_handler_returns_operation_dict(self, order_entity: EntitySchema) -> None:
        tools = generate_crud_tools(order_entity)
        get_tool = next(t for t in tools if t.operation == "get")
        result = get_tool.handler(id="abc-123")
        assert result == {"entity": "Order", "operation": "get", "params": {"id": "abc-123"}}

    def test_invoke_tool_records_in_span(self, order_entity: EntitySchema) -> None:
        tools = generate_crud_tools(order_entity)
        tool = tools[0]
        span = AgentSpan(agent_name="test_agent")
        invoke_tool(tool, span=span, id="123")
        assert len(span.tool_calls) == 1
        record = span.tool_calls[0]
        assert record.tool_name == tool.name
        assert record.success is True
        assert record.duration_ms >= 0
