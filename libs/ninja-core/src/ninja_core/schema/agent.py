"""Agent configuration models for the Agentic Schema Definition."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ReasoningLevel(str, Enum):
    """How much LLM reasoning an agent should apply."""

    NONE = "none"  # Deterministic only (no LLM calls)
    LOW = "low"  # Simple completions
    MEDIUM = "medium"  # Multi-step reasoning
    HIGH = "high"  # Full chain-of-thought / planning


class AgentConfig(BaseModel):
    """Configuration for an Expert Agent attached to a domain."""

    model_provider: str = Field(default="gemini", description="LLM provider identifier (e.g. 'gemini', 'openai').")
    model_name: str = Field(
        default="gemini-2.0-flash",
        description="Model name passed to the provider or LiteLLM.",
    )
    reasoning_level: ReasoningLevel = Field(
        default=ReasoningLevel.MEDIUM, description="How much reasoning the agent should apply."
    )
    tool_permissions: list[str] = Field(
        default_factory=list,
        description="List of tool names the agent is allowed to invoke.",
    )
    system_prompt: str | None = Field(default=None, description="Override system prompt for this agent.")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int | None = Field(default=None, gt=0, description="Maximum tokens for the response.")

    model_config = {"extra": "forbid"}
