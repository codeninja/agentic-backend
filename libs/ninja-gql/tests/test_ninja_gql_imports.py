def test_ninja_gql_imports():
    import ninja_gql

    assert ninja_gql is not None
    assert hasattr(ninja_gql, "GqlGenerator")
    assert hasattr(ninja_gql, "build_schema")
