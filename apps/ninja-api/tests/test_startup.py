"""Tests for startup wiring helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from ninja_api.startup import (
    AgentRouterAdapter,
    load_asd,
    make_agent_router,
    make_orchestrator,
    make_repo_getter,
)
from ninja_core.schema.project import AgenticSchema


class TestLoadAsd:
    def test_loads_schema_from_file(self, asd_file: Path) -> None:
        asd = load_asd(asd_file)
        assert isinstance(asd, AgenticSchema)
        assert asd.project_name == "test-project"

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_asd(tmp_path / "nonexistent.json")


class TestMakeRepoGetter:
    def test_returns_callable(self, sample_asd: AgenticSchema, connections_file: Path) -> None:
        getter = make_repo_getter(sample_asd, connections_path=connections_file)
        assert callable(getter)

    def test_getter_raises_for_unknown_entity(self, sample_asd: AgenticSchema, connections_file: Path) -> None:
        getter = make_repo_getter(sample_asd, connections_path=connections_file)
        with pytest.raises(KeyError, match="NoSuchEntity"):
            getter("NoSuchEntity")

    def test_getter_returns_repo_for_known_entity(self, sample_asd: AgenticSchema, connections_file: Path) -> None:
        getter = make_repo_getter(sample_asd, connections_path=connections_file)
        repo = getter("User")
        # Should return a SQLAdapter (since User is SQL engine).
        assert hasattr(repo, "find_by_id")

    def test_getter_works_without_connections_file(self, sample_asd: AgenticSchema, tmp_path: Path) -> None:
        """When connections.json is missing, ConnectionManager returns empty profiles."""
        getter = make_repo_getter(
            sample_asd,
            connections_path=tmp_path / "no-such-file.json",
        )
        # Should still be callable.
        assert callable(getter)
        # But accessing a repo will fail (no connection profile).
        with pytest.raises(KeyError):
            getter("User")


class TestMakeOrchestrator:
    def test_creates_orchestrator(self, sample_asd: AgenticSchema) -> None:
        orch = make_orchestrator(sample_asd)
        assert orch.coordinator is not None
        assert "Core" in orch.coordinator.domain_names

    def test_orchestrator_has_all_domains(self, sample_asd: AgenticSchema) -> None:
        orch = make_orchestrator(sample_asd)
        assert set(orch.coordinator.domain_names) == {"Core"}


class TestAgentRouterAdapter:
    def test_make_agent_router_returns_adapter(self, sample_asd: AgenticSchema) -> None:
        router = make_agent_router(sample_asd)
        assert isinstance(router, AgentRouterAdapter)

    async def test_ask_delegates_to_fan_out(self, sample_asd: AgenticSchema) -> None:
        router = make_agent_router(sample_asd)
        result = await router.ask("list users", domain="Core")
        # The result should be a dict with domain results.
        assert isinstance(result, dict)
        assert "Core" in result

    async def test_ask_all_domains(self, sample_asd: AgenticSchema) -> None:
        router = make_agent_router(sample_asd)
        result = await router.ask("show everything")
        assert isinstance(result, dict)
