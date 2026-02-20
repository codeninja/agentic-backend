"""Test that all public exports are importable."""


def test_ninja_persistence_imports():
    import ninja_persistence

    assert ninja_persistence is not None


def test_public_api_exports():
    from ninja_persistence import (
        AdapterRegistry,
        ChromaVectorAdapter,
        ConnectionManager,
        ConnectionProfile,
        EmbeddingStrategy,
        GraphAdapter,
        MilvusVectorAdapter,
        MongoAdapter,
        Repository,
        SQLAdapter,
    )

    assert all(
        [
            AdapterRegistry,
            ChromaVectorAdapter,
            ConnectionManager,
            ConnectionProfile,
            EmbeddingStrategy,
            GraphAdapter,
            MilvusVectorAdapter,
            MongoAdapter,
            Repository,
            SQLAdapter,
        ]
    )
