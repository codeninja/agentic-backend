"""Test that the ninja_graph package imports correctly."""


def test_ninja_graph_imports():
    import ninja_graph

    assert ninja_graph is not None


def test_public_api():
    from ninja_graph import GraphBackend, GraphSchema, map_asd_to_graph_schema

    assert GraphBackend is not None
    assert GraphSchema is not None
    assert map_asd_to_graph_schema is not None
