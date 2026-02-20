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
    """Generate ADK DataAgent and DomainAgent definitions."""
    paths = generate_agents([order_entity, product_entity], [billing_domain, inventory_domain], tmp_path)

    assert len(paths) > 0
    agents_dir = tmp_path / "_generated" / "agents"
    assert (agents_dir / "order_agent.py").exists()
    assert (agents_dir / "product_agent.py").exists()
    assert (agents_dir / "billing_agent.py").exists()
    assert (agents_dir / "inventory_agent.py").exists()

    # Check data agent content — ADK BaseAgent subclass
    order_agent = (agents_dir / "order_agent.py").read_text()
    assert "from google.adk.agents import BaseAgent" in order_agent
    assert "class OrderDataAgent(BaseAgent):" in order_agent
    assert "async def _run_async_impl(self, ctx" in order_agent
    assert "ORDER_TOOLS" in order_agent
    assert "AUTO-GENERATED" in order_agent

    # Check CRUD tool functions are plain functions with docstrings
    assert "def order_get(id: str)" in order_agent
    assert "def order_list(limit: int = 25" in order_agent
    assert "def order_create(" in order_agent
    assert "def order_update(id: str" in order_agent
    assert "def order_delete(id: str)" in order_agent
    assert "def order_search_semantic(query: str" in order_agent
    assert '"""Retrieve a single Order by ID."""' in order_agent

    # Check domain agent content — ADK LlmAgent
    billing_agent = (agents_dir / "billing_agent.py").read_text()
    assert "from google.adk.agents import LlmAgent" in billing_agent
    assert "billing_domain_agent = LlmAgent(" in billing_agent
    assert 'name="domain_agent_billing"' in billing_agent
    assert "BILLING_TOOLS" in billing_agent
    assert "BILLING_SUB_AGENTS" in billing_agent
    assert "OrderDataAgent" in billing_agent

    # Check inventory domain agent uses correct model for LOW reasoning
    inventory_agent = (agents_dir / "inventory_agent.py").read_text()
    assert "gemini-2.0-flash" in inventory_agent
    assert "inventory_domain_agent = LlmAgent(" in inventory_agent
    assert "ProductDataAgent" in inventory_agent

    # Check __init__.py re-exports
    init_content = (agents_dir / "__init__.py").read_text()
    assert "from .order_agent import OrderDataAgent" in init_content
    assert "from .billing_agent import billing_domain_agent" in init_content


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


def test_data_agent_tools_are_plain_functions(tmp_path, order_entity):
    """Generated tools are plain functions with type hints and docstrings."""
    generate_agents([order_entity], [], tmp_path)
    agents_dir = tmp_path / "_generated" / "agents"
    content = (agents_dir / "order_agent.py").read_text()

    # Each tool should be a standalone function (not a class method)
    assert "def order_get(" in content
    assert "def order_list(" in content
    assert "def order_create(" in content
    assert "def order_update(" in content
    assert "def order_delete(" in content
    assert "def order_search_semantic(" in content

    # Functions should have docstrings
    assert '"""Retrieve a single Order by ID."""' in content
    assert '"""List Order records' in content
    assert '"""Create a new Order record."""' in content
    assert '"""Update an existing Order record."""' in content
    assert '"""Delete a Order record by ID."""' in content
    assert '"""Semantic search across Order records."""' in content

    # Functions should have return type hints
    assert "-> dict[str, Any]" in content


def test_domain_agent_uses_llm_agent(tmp_path, order_entity, billing_domain):
    """Generated domain agent uses LlmAgent from google.adk.agents."""
    generate_agents([order_entity], [billing_domain], tmp_path)
    agents_dir = tmp_path / "_generated" / "agents"
    content = (agents_dir / "billing_agent.py").read_text()

    assert "from google.adk.agents import LlmAgent" in content
    assert "billing_domain_agent = LlmAgent(" in content
    assert "model=" in content
    assert "description=" in content
    assert "instruction=" in content
    assert "tools=" in content
    assert "sub_agents=" in content
