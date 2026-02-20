"""Smoke test — verify that the public API is importable."""


def test_ninja_agents_imports():
    import ninja_agents

    assert ninja_agents is not None


def test_adk_types_exported():
    from ninja_agents import (
        CoordinatorAgent,
        DataAgent,
        DomainAgent,
        Orchestrator,
        TraceContext,
        create_coordinator_agent,
        create_domain_agent,
        generate_crud_tools,
    )

    assert DataAgent is not None
    assert DomainAgent is not None
    assert CoordinatorAgent is not None
    assert Orchestrator is not None
    assert TraceContext is not None
    assert create_domain_agent is not None
    assert create_coordinator_agent is not None
    assert generate_crud_tools is not None
