"""Tests for the SetupAssistant and agent creation."""

from __future__ import annotations

from unittest.mock import patch

from google.adk.agents import LlmAgent
from ninja_core.schema.project import AgenticSchema
from ninja_setup_assistant.assistant import (
    APP_NAME,
    SetupAssistant,
    create_setup_agent,
    has_api_key,
)
from ninja_setup_assistant.tools import SchemaWorkspace

# ---------------------------------------------------------------------------
# create_setup_agent
# ---------------------------------------------------------------------------


class TestCreateSetupAgent:
    def test_returns_llm_agent(self) -> None:
        ws = SchemaWorkspace(schema=AgenticSchema(project_name="test"))
        agent = create_setup_agent(ws)
        assert isinstance(agent, LlmAgent)

    def test_agent_name(self) -> None:
        ws = SchemaWorkspace(schema=AgenticSchema(project_name="test"))
        agent = create_setup_agent(ws)
        assert agent.name == "ninja_setup_assistant"

    def test_agent_has_tools(self) -> None:
        ws = SchemaWorkspace(schema=AgenticSchema(project_name="test"))
        agent = create_setup_agent(ws)
        assert len(agent.tools) == 6

    def test_agent_uses_specified_model(self) -> None:
        ws = SchemaWorkspace(schema=AgenticSchema(project_name="test"))
        agent = create_setup_agent(ws, model="gemini-2.0-flash")
        assert agent.model == "gemini-2.0-flash"

    def test_agent_has_instruction(self) -> None:
        ws = SchemaWorkspace(schema=AgenticSchema(project_name="test"))
        agent = create_setup_agent(ws)
        assert agent.instruction is not None

    def test_tools_share_workspace(self) -> None:
        ws = SchemaWorkspace(schema=AgenticSchema(project_name="test"))
        agent = create_setup_agent(ws)
        # Call the first tool (add_entity) and verify it modifies the shared workspace
        add_tool = next(t for t in agent.tools if callable(t) and getattr(t, "__name__", "") == "adk_add_entity")
        result = add_tool(name="User", fields=[{"name": "id", "field_type": "uuid", "primary_key": "true"}])
        assert "Added entity" in result
        assert len(ws.schema.entities) == 1


# ---------------------------------------------------------------------------
# has_api_key
# ---------------------------------------------------------------------------


class TestHasApiKey:
    def test_no_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert has_api_key() is False

    def test_google_api_key(self) -> None:
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            assert has_api_key() is True

    def test_google_genai_key(self) -> None:
        with patch.dict("os.environ", {"GOOGLE_GENAI_API_KEY": "test-key"}):
            assert has_api_key() is True


# ---------------------------------------------------------------------------
# SetupAssistant
# ---------------------------------------------------------------------------


class TestSetupAssistant:
    def test_creates_workspace(self) -> None:
        assistant = SetupAssistant(project_name="test")
        assert assistant.workspace.schema.project_name == "test"
        assert assistant.workspace.schema.entities == []

    def test_creates_agent(self) -> None:
        assistant = SetupAssistant(project_name="test")
        assert isinstance(assistant.agent, LlmAgent)

    def test_stub_mode_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assistant = SetupAssistant(project_name="test")
            assert assistant.is_stub is True

    async def test_stub_chat_response(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assistant = SetupAssistant(project_name="test")
            response = await assistant.chat("Hello")
            assert "stub mode" in response

    def test_app_name_constant(self) -> None:
        assert APP_NAME == "ninja_setup_assistant"

    def test_get_tool_functions(self) -> None:
        assistant = SetupAssistant(project_name="test")
        tools = assistant.get_tool_functions()
        assert "adk_add_entity" in tools
        assert "adk_review_schema" in tools
        assert len(tools) == 6

    def test_tool_functions_modify_workspace(self) -> None:
        assistant = SetupAssistant(project_name="test")
        tools = assistant.get_tool_functions()
        result = tools["adk_add_entity"](name="User", fields=[{"name": "id", "field_type": "uuid", "primary_key": "true"}])
        assert "Added entity" in result
        assert len(assistant.workspace.schema.entities) == 1
