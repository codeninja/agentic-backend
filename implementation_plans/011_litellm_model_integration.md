# Implementation Plan 011: LiteLLM & Model Integration

> **Milestone**: 1 — The Foundation
> **Tickets**: (New)

## Objective
Integrate LiteLLM as the universal model adapter within the ADK agent framework. Every agent in the Ninja Stack should be able to target any LLM provider (Gemini, OpenAI, Anthropic, Ollama, etc.) through a unified configuration, with Gemini as the default.

## Requirements
- **Default to Gemini**: All generated agents use Google Gemini unless overridden.
- **Per-agent model config**: The ASD's `AgentConfig` specifies which model each agent uses.
- **LiteLLM as the bridge**: ADK agents use LiteLLM connectors for non-Gemini providers.
- **Local model support**: Ollama integration for on-prem/air-gapped deployments.
- **Cost tracking**: Log token usage and estimated cost per agent invocation.
- **Fallback chains**: Configure primary → fallback model (e.g., Gemini Pro → Gemini Flash → local).

## Configuration (`.ninjastack/models.json`)
```json
{
  "default": "gemini/gemini-2.5-pro",
  "fallback": "gemini/gemini-2.5-flash",
  "agents": {
    "billing-domain": "gemini/gemini-2.5-pro",
    "data-user": "gemini/gemini-2.5-flash"
  },
  "providers": {
    "openai": { "api_key_env": "OPENAI_API_KEY" },
    "anthropic": { "api_key_env": "ANTHROPIC_API_KEY" },
    "ollama": { "base_url": "http://localhost:11434" }
  }
}
```

## File Structure
```
libs/ninja-models/
├── pyproject.toml
├── src/ninja_models/
│   ├── __init__.py
│   ├── config.py             # Read .ninjastack/models.json
│   ├── resolver.py           # Resolve agent → model (with fallback)
│   ├── litellm_bridge.py     # ADK ↔ LiteLLM adapter
│   ├── cost_tracker.py       # Token usage and cost logging
│   └── providers/
│       ├── gemini.py
│       ├── openai.py
│       ├── anthropic.py
│       └── ollama.py
└── tests/
```

## Acceptance Criteria
- [ ] Default agent uses Gemini without any explicit config.
- [ ] An agent configured with `openai/gpt-4o` routes through LiteLLM successfully.
- [ ] Fallback chain triggers when primary model returns an error.
- [ ] Token usage is logged per agent invocation.
- [ ] Ollama-backed agent works in a fully offline environment.

## Dependencies
- Plan 002 (ASD Core Models — AgentConfig model definition)
