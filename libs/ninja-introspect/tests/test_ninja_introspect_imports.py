"""Smoke tests for ninja-introspect public API imports."""


def test_ninja_introspect_imports():
    import ninja_introspect

    assert ninja_introspect is not None


def test_public_api_exports():
    from ninja_introspect import (
        GraphProvider,
        IntrospectionEngine,
        IntrospectionProvider,
        IntrospectionResult,
        MongoProvider,
        SQLProvider,
        VectorProvider,
    )

    assert IntrospectionEngine is not None
    assert IntrospectionProvider is not None
    assert IntrospectionResult is not None
    assert SQLProvider is not None
    assert MongoProvider is not None
    assert GraphProvider is not None
    assert VectorProvider is not None
