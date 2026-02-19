"""Tests for ninja_models.resolver."""

from ninja_models.config import DEFAULT_MODEL, ModelsConfig
from ninja_models.resolver import ModelResolver


class TestModelResolver:
    def test_resolve_default_no_agent(self):
        resolver = ModelResolver(ModelsConfig())
        assert resolver.resolve() == DEFAULT_MODEL

    def test_resolve_default_for_unknown_agent(self):
        resolver = ModelResolver(ModelsConfig())
        assert resolver.resolve("unknown-agent") == DEFAULT_MODEL

    def test_resolve_agent_mapping(self):
        config = ModelsConfig(agents={"billing-domain": "openai/gpt-4o"})
        resolver = ModelResolver(config)
        assert resolver.resolve("billing-domain") == "openai/gpt-4o"

    def test_resolve_agent_falls_back_to_default(self):
        config = ModelsConfig(
            default="gemini/gemini-2.5-pro",
            agents={"billing-domain": "openai/gpt-4o"},
        )
        resolver = ModelResolver(config)
        assert resolver.resolve("other-agent") == "gemini/gemini-2.5-pro"

    def test_fallback(self):
        config = ModelsConfig(fallback="gemini/gemini-2.5-flash")
        resolver = ModelResolver(config)
        assert resolver.fallback() == "gemini/gemini-2.5-flash"

    def test_fallback_none(self):
        config = ModelsConfig(fallback=None)
        resolver = ModelResolver(config)
        assert resolver.fallback() is None

    def test_resolve_chain_with_fallback(self):
        config = ModelsConfig(
            default="gemini/gemini-2.5-pro",
            fallback="gemini/gemini-2.5-flash",
        )
        resolver = ModelResolver(config)
        chain = resolver.resolve_chain()
        assert chain == ["gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash"]

    def test_resolve_chain_no_fallback(self):
        config = ModelsConfig(fallback=None)
        resolver = ModelResolver(config)
        chain = resolver.resolve_chain()
        assert chain == [DEFAULT_MODEL]

    def test_resolve_chain_deduplicates(self):
        config = ModelsConfig(
            default="gemini/gemini-2.5-pro",
            fallback="gemini/gemini-2.5-pro",
        )
        resolver = ModelResolver(config)
        chain = resolver.resolve_chain()
        assert chain == ["gemini/gemini-2.5-pro"]

    def test_resolve_chain_with_agent(self):
        config = ModelsConfig(
            default="gemini/gemini-2.5-pro",
            fallback="gemini/gemini-2.5-flash",
            agents={"billing": "openai/gpt-4o"},
        )
        resolver = ModelResolver(config)
        chain = resolver.resolve_chain("billing")
        assert chain == ["openai/gpt-4o", "gemini/gemini-2.5-flash"]
