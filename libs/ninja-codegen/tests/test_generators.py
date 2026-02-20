"""Tests for individual code generators."""

from __future__ import annotations

from ninja_codegen.generators.agents import generate_agents
from ninja_codegen.generators.apps import generate_app_shell
from ninja_codegen.generators.graphql import generate_graphql
from ninja_codegen.generators.models import generate_models


def test_generate_models(tmp_path, order_entity, product_entity):
    """Generate Pydantic models for entities."""
    paths = generate_models([order_entity, product_entity], tmp_path)

    assert len(paths) > 0
    models_dir = tmp_path / "_generated" / "models"
    assert (models_dir / "order.py").exists()
    assert (models_dir / "product.py").exists()
    assert (models_dir / "__init__.py").exists()

    # Check content
    order_content = (models_dir / "order.py").read_text()
    assert "class Order(BaseModel):" in order_content
    assert "AUTO-GENERATED" in order_content
    assert "UUID" in order_content
    assert "customer_id" in order_content

    product_content = (models_dir / "product.py").read_text()
    assert "class Product(BaseModel):" in product_content
    assert "in_stock: bool" in product_content

    # Check __init__.py re-exports
    init_content = (models_dir / "__init__.py").read_text()
    assert "from .order import Order" in init_content
    assert "from .product import Product" in init_content


def test_generate_agents(tmp_path, order_entity, product_entity, billing_domain, inventory_domain):
    """Generate DataAgent, DomainAgent, and CoordinatorAgent code using real ADK classes."""
    paths = generate_agents([order_entity, product_entity], [billing_domain, inventory_domain], tmp_path)

    assert len(paths) > 0
    agents_dir = tmp_path / "_generated" / "agents"
    assert (agents_dir / "order_agent.py").exists()
    assert (agents_dir / "product_agent.py").exists()
    assert (agents_dir / "billing_agent.py").exists()
    assert (agents_dir / "inventory_agent.py").exists()
    assert (agents_dir / "coordinator_agent.py").exists()

    # Check data agent imports real ADK classes
    order_agent = (agents_dir / "order_agent.py").read_text()
    assert "from ninja_agents.base import DataAgent" in order_agent
    assert "from ninja_agents.tools import generate_crud_tools" in order_agent
    assert "ORDER_ENTITY" in order_agent
    assert "order_data_agent = DataAgent(" in order_agent
    assert "generate_crud_tools(ORDER_ENTITY)" in order_agent
    assert "AUTO-GENERATED" in order_agent

    # Check domain agent imports real ADK classes
    billing_agent = (agents_dir / "billing_agent.py").read_text()
    assert "from ninja_agents.base import DataAgent, DomainAgent" in billing_agent
    assert "BILLING_DOMAIN" in billing_agent
    assert "create_billing_domain_agent" in billing_agent
    assert "-> DomainAgent:" in billing_agent
    assert "ReasoningLevel.MEDIUM" in billing_agent

    # Check coordinator agent wires domains
    coordinator = (agents_dir / "coordinator_agent.py").read_text()
    assert "from ninja_agents.base import CoordinatorAgent, DomainAgent" in coordinator
    assert "create_coordinator" in coordinator
    assert "create_billing_domain_agent" in coordinator
    assert "create_inventory_domain_agent" in coordinator
    assert "ReasoningLevel.HIGH" in coordinator

    # Check __init__.py re-exports
    init_content = (agents_dir / "__init__.py").read_text()
    assert "order_data_agent" in init_content
    assert "product_data_agent" in init_content
    assert "create_billing_domain_agent" in init_content
    assert "create_inventory_domain_agent" in init_content
    assert "create_coordinator" in init_content


def test_generate_graphql(tmp_path, order_entity, product_entity):
    """Generate GraphQL types and resolvers."""
    paths = generate_graphql([order_entity, product_entity], tmp_path)

    assert len(paths) > 0
    gql_dir = tmp_path / "_generated" / "graphql"
    assert (gql_dir / "order_gql.py").exists()
    assert (gql_dir / "product_gql.py").exists()

    order_gql = (gql_dir / "order_gql.py").read_text()
    assert "@strawberry.type" in order_gql
    assert "class OrderType:" in order_gql
    assert "class OrderInput:" in order_gql
    assert "class OrderQuery:" in order_gql
    assert "class OrderMutation:" in order_gql


def test_generate_app_shell(tmp_path):
    """Generate FastAPI app shell."""
    path = generate_app_shell("MyProject", tmp_path)

    assert path.exists()
    content = path.read_text()
    assert "FastAPI" in content
    assert "MyProject" in content
    assert "healthz" in content
    assert "AUTO-GENERATED" in content

    # Check __init__.py
    init = (tmp_path / "_generated" / "app" / "__init__.py").read_text()
    assert "from .main import app" in init


def test_generate_models_idempotent(tmp_path, order_entity):
    """Running model generation twice produces identical output."""
    generate_models([order_entity], tmp_path)
    content_first = (tmp_path / "_generated" / "models" / "order.py").read_text()

    generate_models([order_entity], tmp_path)
    content_second = (tmp_path / "_generated" / "models" / "order.py").read_text()

    assert content_first == content_second
