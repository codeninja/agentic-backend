"""Assemble generated Strawberry types into a working ``strawberry.Schema``.

The main entry point is :func:`build_schema`, which takes an ASD and an
optional repository-getter callback, and returns a fully executable
``strawberry.Schema`` with configurable security extensions.
"""

from typing import Any, Callable

import strawberry
from ninja_core.schema.project import AgenticSchema
from ninja_persistence.protocols import Repository

from ninja_gql.generator import GqlGenerator
from ninja_gql.resolvers.agent import AgentRouter, make_agent_query_resolver
from ninja_gql.resolvers.crud import (
    _snake,
    make_create_resolver,
    make_delete_resolver,
    make_get_resolver,
    make_list_resolver,
    make_update_resolver,
)
from ninja_gql.resolvers.semantic import make_search_resolver
from ninja_gql.resolvers.subscription import make_subscription_resolver
from ninja_gql.security import GraphQLSecurityConfig, build_security_extensions


def build_schema(
    asd: AgenticSchema,
    repo_getter: Callable[[str], Repository[Any]] | None = None,
    agent_router: AgentRouter | None = None,
    security_config: GraphQLSecurityConfig | None = None,
) -> strawberry.Schema:
    """Build a Strawberry ``Schema`` from an Agentic Schema Definition.

    Parameters
    ----------
    asd:
        The project's ASD.
    repo_getter:
        A callable ``(entity_name) -> Repository``.  When ``None`` a stub
        that raises at call-time is used (useful for schema-only validation).
    agent_router:
        Optional agent router for ``ask_*`` queries.
    security_config:
        Optional security configuration.  When ``None``, default security
        settings are applied (introspection enabled, depth limit 10,
        complexity limit 1000).
    """
    gen = GqlGenerator(asd)
    types = gen.generate_types()
    gen.generate_input_types()

    if repo_getter is None:

        def _no_repo(name: str) -> Repository[Any]:
            raise RuntimeError(f"No repository configured for {name}")

        repo_getter = _no_repo

    # -- build Query fields --------------------------------------------------
    query_annotations: dict[str, Any] = {}
    query_ns: dict[str, Any] = {"__annotations__": query_annotations}

    for entity in asd.entities:
        gql_type = types[entity.name]
        snake = _snake(entity.name)

        # get
        get_name = f"get_{snake}"
        get_fn = make_get_resolver(entity, gql_type, repo_getter)
        query_ns[get_name] = strawberry.field(resolver=get_fn)

        # list
        list_name = f"list_{snake}"
        list_fn = make_list_resolver(entity, gql_type, repo_getter)
        query_ns[list_name] = strawberry.field(resolver=list_fn)

        # semantic search (only for entities with embeddable fields)
        if gen.has_embeddable_fields(entity):
            search_name = f"search_{snake}"
            search_fn = make_search_resolver(entity, gql_type, repo_getter)
            query_ns[search_name] = strawberry.field(resolver=search_fn)

    # agent queries per domain
    for domain in asd.domains:
        ask_name = f"ask_{domain.name.lower().replace(' ', '_')}"
        ask_fn = make_agent_query_resolver(domain.name, agent_router)
        query_ns[ask_name] = strawberry.field(resolver=ask_fn)

    query_cls = type("Query", (), query_ns)
    Query = strawberry.type(query_cls, description="Auto-generated root Query")

    # -- build entity→domain lookup for authorization -------------------------
    entity_domain: dict[str, str] = {}
    for domain in asd.domains:
        for ent_name in domain.entities:
            entity_domain[ent_name] = domain.name

    # -- build Mutation fields -----------------------------------------------
    mutation_annotations: dict[str, Any] = {}
    mutation_ns: dict[str, Any] = {"__annotations__": mutation_annotations}

    for entity in asd.entities:
        gql_type = types[entity.name]
        snake = _snake(entity.name)
        domain = entity_domain.get(entity.name)

        create_fn = make_create_resolver(entity, gql_type, repo_getter, domain=domain)
        mutation_ns[f"create_{snake}"] = strawberry.mutation(resolver=create_fn)

        update_fn = make_update_resolver(entity, gql_type, repo_getter, domain=domain)
        mutation_ns[f"update_{snake}"] = strawberry.mutation(resolver=update_fn)

        delete_fn = make_delete_resolver(entity, repo_getter, domain=domain)
        mutation_ns[f"delete_{snake}"] = strawberry.mutation(resolver=delete_fn)

    mutation_cls = type("Mutation", (), mutation_ns)
    Mutation = strawberry.type(mutation_cls, description="Auto-generated root Mutation")

    # -- build Subscription fields -------------------------------------------
    sub_annotations: dict[str, Any] = {}
    sub_ns: dict[str, Any] = {"__annotations__": sub_annotations}

    for entity in asd.entities:
        snake = _snake(entity.name)
        sub_fn = make_subscription_resolver(entity)
        sub_ns[f"on_{snake}_changed"] = strawberry.subscription(resolver=sub_fn)

    sub_cls = type("Subscription", (), sub_ns)
    Subscription = strawberry.type(sub_cls, description="Auto-generated root Subscription")

    # -- build security extensions -------------------------------------------
    extensions = build_security_extensions(security_config)

    return strawberry.Schema(
        query=Query,
        mutation=Mutation,
        subscription=Subscription,
        extensions=extensions,
    )


def build_schema_sdl(asd: AgenticSchema) -> str:
    """Return the generated schema as an SDL string (no resolvers needed)."""
    schema = build_schema(asd)
    return str(schema)
