"""Tests for system prompts."""

from ninja_setup_assistant.prompts import (
    BOLT_ON_FOLLOWUP,
    GREENFIELD_FOLLOWUP,
    SETUP_ASSISTANT_PROMPT,
    SYSTEM_PROMPT,
)


class TestPrompts:
    def test_system_prompt_not_empty(self) -> None:
        assert len(SETUP_ASSISTANT_PROMPT) > 100

    def test_system_prompt_mentions_tools(self) -> None:
        assert "add_entity" in SETUP_ASSISTANT_PROMPT
        assert "add_relationship" in SETUP_ASSISTANT_PROMPT
        assert "create_domain" in SETUP_ASSISTANT_PROMPT
        assert "review_schema" in SETUP_ASSISTANT_PROMPT
        assert "confirm_schema" in SETUP_ASSISTANT_PROMPT
        assert "introspect_database" in SETUP_ASSISTANT_PROMPT

    def test_system_prompt_mentions_workflows(self) -> None:
        assert "greenfield" in SETUP_ASSISTANT_PROMPT.lower()
        assert "bolt-on" in SETUP_ASSISTANT_PROMPT.lower()

    def test_system_prompt_has_design_guidelines(self) -> None:
        assert "PascalCase" in SETUP_ASSISTANT_PROMPT
        assert "snake_case" in SETUP_ASSISTANT_PROMPT

    def test_backward_compat_alias(self) -> None:
        assert SYSTEM_PROMPT is SETUP_ASSISTANT_PROMPT

    def test_greenfield_followup(self) -> None:
        assert "scratch" in GREENFIELD_FOLLOWUP

    def test_bolt_on_followup(self) -> None:
        assert "connection string" in BOLT_ON_FOLLOWUP
