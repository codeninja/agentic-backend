"""Tests for the SetupAssistant and tool dispatch."""

from __future__ import annotations

import pytest
from ninja_core.schema.project import AgenticSchema
from ninja_setup_assistant.assistant import (
    AgentResponse,
    SetupAssistant,
    StubProvider,
    dispatch_tool_call,
)
from ninja_setup_assistant.tools import SchemaWorkspace, add_entity

# ---------------------------------------------------------------------------
# dispatch_tool_call
# ---------------------------------------------------------------------------


class TestDispatchToolCall:
    @pytest.fixture()
    def workspace(self) -> SchemaWorkspace:
        return SchemaWorkspace(schema=AgenticSchema(project_name="test"))

    async def test_dispatch_add_entity(self, workspace: SchemaWorkspace) -> None:
        result = await dispatch_tool_call(
            workspace,
            "add_entity",
            {"name": "User", "fields": [{"name": "id", "field_type": "uuid"}]},
        )
        assert "Added entity" in result
        assert len(workspace.schema.entities) == 1

    async def test_dispatch_review_schema(self, workspace: SchemaWorkspace) -> None:
        result = await dispatch_tool_call(workspace, "review_schema", {})
        assert "No entities" in result

    async def test_dispatch_unknown_tool(self, workspace: SchemaWorkspace) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            await dispatch_tool_call(workspace, "nonexistent", {})

    async def test_dispatch_confirm_schema(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        result = await dispatch_tool_call(workspace, "confirm_schema", {})
        assert "test" in result  # project_name

    async def test_dispatch_add_relationship(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        add_entity(workspace, name="Post", fields=[{"name": "id", "field_type": "uuid"}])
        result = await dispatch_tool_call(
            workspace,
            "add_relationship",
            {"name": "user_posts", "source_entity": "Post", "target_entity": "User"},
        )
        assert "Added relationship" in result

    async def test_dispatch_create_domain(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        result = await dispatch_tool_call(
            workspace,
            "create_domain",
            {"name": "Users", "entities": ["User"]},
        )
        assert "Created domain" in result


# ---------------------------------------------------------------------------
# StubProvider
# ---------------------------------------------------------------------------


class TestStubProvider:
    async def test_stub_returns_message(self) -> None:
        provider = StubProvider()
        response = await provider.send_message("hello")
        assert "stub mode" in response.text
        assert response.tool_calls == []


# ---------------------------------------------------------------------------
# SetupAssistant with StubProvider
# ---------------------------------------------------------------------------


class TestSetupAssistant:
    def test_creates_with_stub_provider(self) -> None:
        assistant = SetupAssistant(project_name="test")
        assert isinstance(assistant.provider, StubProvider)
        assert assistant.workspace.schema.project_name == "test"

    async def test_chat_returns_stub_response(self) -> None:
        assistant = SetupAssistant(project_name="test")
        response = await assistant.chat("Hello")
        assert "stub mode" in response

    async def test_workspace_is_accessible(self) -> None:
        assistant = SetupAssistant(project_name="my-app")
        assert assistant.workspace.schema.project_name == "my-app"
        assert assistant.workspace.schema.entities == []


# ---------------------------------------------------------------------------
# SetupAssistant with a mock provider that returns tool calls
# ---------------------------------------------------------------------------


class MockToolProvider:
    """A mock provider that returns a tool call on the first message, then text."""

    def __init__(self) -> None:
        self._call_count = 0

    async def send_message(self, message: str) -> AgentResponse:
        self._call_count += 1
        if self._call_count == 1:
            return AgentResponse(
                text="Let me add that entity for you.",
                tool_calls=[
                    {
                        "name": "add_entity",
                        "arguments": {
                            "name": "User",
                            "fields": [
                                {"name": "id", "field_type": "uuid", "primary_key": True},
                                {"name": "email", "field_type": "string"},
                            ],
                        },
                    }
                ],
            )
        return AgentResponse(text="I've added the User entity with id and email fields.")


class TestSetupAssistantWithToolCalls:
    async def test_tool_calls_are_executed(self) -> None:
        assistant = SetupAssistant(project_name="test", provider=MockToolProvider())
        response = await assistant.chat("Add a User entity with id and email")

        # Tool should have been executed
        assert len(assistant.workspace.schema.entities) == 1
        assert assistant.workspace.schema.entities[0].name == "User"

        # Response should contain both the initial text and follow-up
        assert "User entity" in response


class MockMultiToolProvider:
    """Provider that returns multiple tool calls."""

    def __init__(self) -> None:
        self._call_count = 0

    async def send_message(self, message: str) -> AgentResponse:
        self._call_count += 1
        if self._call_count == 1:
            return AgentResponse(
                text="",
                tool_calls=[
                    {
                        "name": "add_entity",
                        "arguments": {
                            "name": "User",
                            "fields": [{"name": "id", "field_type": "uuid"}],
                        },
                    },
                    {
                        "name": "add_entity",
                        "arguments": {
                            "name": "Post",
                            "fields": [{"name": "id", "field_type": "uuid"}],
                        },
                    },
                ],
            )
        return AgentResponse(text="Added User and Post entities.")


class TestMultipleToolCalls:
    async def test_multiple_tool_calls(self) -> None:
        assistant = SetupAssistant(project_name="test", provider=MockMultiToolProvider())
        response = await assistant.chat("Create User and Post entities")
        assert len(assistant.workspace.schema.entities) == 2
        assert "Added User and Post" in response
