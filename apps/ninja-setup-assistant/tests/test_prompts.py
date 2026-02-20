"""Tests for system prompts."""

from ninja_setup_assistant.prompts import BOLT_ON_FOLLOWUP, GREENFIELD_FOLLOWUP, SYSTEM_PROMPT


class TestPrompts:
    def test_system_prompt_not_empty(self) -> None:
        assert len(SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_tools(self) -> None:
        assert "add_entity" in SYSTEM_PROMPT
        assert "add_relationship" in SYSTEM_PROMPT
        assert "create_domain" in SYSTEM_PROMPT
        assert "review_schema" in SYSTEM_PROMPT
        assert "confirm_schema" in SYSTEM_PROMPT
        assert "introspect_database" in SYSTEM_PROMPT

    def test_greenfield_followup(self) -> None:
        assert "scratch" in GREENFIELD_FOLLOWUP

    def test_bolt_on_followup(self) -> None:
        assert "connection string" in BOLT_ON_FOLLOWUP
