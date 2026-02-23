"""Tests that generated UI templates use parameterized GraphQL queries.

Verifies the fix for GitHub issue #85: GraphQL query injection in generated
CRUD UI. All user-controlled values (IDs, patch data, search queries) must
be passed as GraphQL variables, never interpolated into query strings.
"""

from __future__ import annotations

import re

from ninja_ui.chat.generator import ChatGenerator
from ninja_ui.crud.generator import CrudGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Patterns that indicate unsafe string interpolation of user input into
# GraphQL query strings.  These look for template-literal interpolation of
# JS variables that hold user data (id, patch, input, query, text) inside
# a gqlQuery call's first argument.
_UNSAFE_INTERPOLATION = re.compile(
    r"gqlQuery\(`[^`]*\$\{(?:id|patch|patchJson|inputJson|query|text|pkVal)[^`]*`\s*\)",
)

# Pattern that matches the old quote-escaping trick:  .replace(/"/g, '\\"')
_MANUAL_ESCAPE = re.compile(r'\.replace\(/"/g')

# Pattern matching inline onclick handlers that interpolate variables via
# template literals (e.g.  onclick="deleteRecord('${pkVal}')").
_INLINE_ONCLICK_INTERPOLATION = re.compile(
    r"""onclick=["'][^"']*\$\{[^}]+\}[^"']*["']""",
)


def _generate_crud_html(sample_asd, entity, tmp_path) -> str:
    """Generate a CRUD entity page and return its HTML content."""
    gen = CrudGenerator(sample_asd)
    path = gen.generate_entity_page(entity, tmp_path)
    return path.read_text()


def _generate_chat_html(sample_asd, tmp_path) -> str:
    """Generate the chat page and return its HTML content."""
    gen = ChatGenerator(sample_asd)
    gen.generate(tmp_path)
    return (tmp_path / "chat" / "index.html").read_text()


# ---------------------------------------------------------------------------
# CRUD template tests
# ---------------------------------------------------------------------------


class TestCrudGraphQLVariables:
    """Verify CRUD templates use GraphQL variables for all user input."""

    def test_no_unsafe_interpolation_in_crud(self, sample_asd, customer_entity, tmp_path):
        """No user-controlled JS variable should be interpolated into a query string."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        matches = _UNSAFE_INTERPOLATION.findall(html)
        assert matches == [], f"Found unsafe GraphQL interpolation: {matches}"

    def test_no_manual_quote_escaping(self, sample_asd, customer_entity, tmp_path):
        """The old .replace(/\"/g, ...) workaround must not appear."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        matches = _MANUAL_ESCAPE.findall(html)
        assert matches == [], f"Found manual quote escaping: {matches}"

    def test_no_inline_onclick_interpolation(self, sample_asd, customer_entity, tmp_path):
        """Action buttons must not interpolate variables into onclick attributes."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        matches = _INLINE_ONCLICK_INTERPOLATION.findall(html)
        assert matches == [], f"Found inline onclick interpolation: {matches}"

    def test_update_mutation_uses_variables(self, sample_asd, customer_entity, tmp_path):
        """The update mutation must declare $id and $patch as GraphQL variables."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        assert "mutation UpdateEntity($id: String!, $patch: JSON!)" in html

    def test_create_mutation_uses_variables(self, sample_asd, customer_entity, tmp_path):
        """The create mutation must declare $input as a GraphQL variable."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        assert "mutation CreateEntity($input: JSON!)" in html

    def test_delete_mutation_uses_variables(self, sample_asd, customer_entity, tmp_path):
        """The delete mutation must declare $id as a GraphQL variable."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        assert "mutation DeleteEntity($id: String!)" in html

    def test_list_query_uses_variables(self, sample_asd, customer_entity, tmp_path):
        """The list query must use $limit and $offset variables."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        assert "query ListEntities($limit: Int!, $offset: Int!)" in html

    def test_semantic_search_uses_variables(self, sample_asd, product_entity, tmp_path):
        """Semantic search must pass the query string as a GraphQL variable."""
        html = _generate_crud_html(sample_asd, product_entity, tmp_path)
        assert "query SearchEntities($query: String!)" in html

    def test_gqlquery_accepts_variables_param(self, sample_asd, customer_entity, tmp_path):
        """The gqlQuery function must accept and forward a variables parameter."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        assert "async function gqlQuery(query, variables)" in html
        assert "JSON.stringify({ query, variables: variables || {} })" in html

    def test_action_buttons_use_event_listeners(self, sample_asd, customer_entity, tmp_path):
        """Action buttons must use addEventListener, not inline onclick with interpolation."""
        html = _generate_crud_html(sample_asd, customer_entity, tmp_path)
        assert "addEventListener" in html
        # The old pattern used innerHTML with onclick="${pkVal}" — should be gone
        assert "onclick=\"deleteRecord('" not in html
        assert "onclick=\"saveEdit('" not in html


# ---------------------------------------------------------------------------
# Chat template tests
# ---------------------------------------------------------------------------


class TestChatGraphQLVariables:
    """Verify chat template uses GraphQL variables for user input."""

    def test_no_unsafe_interpolation_in_chat(self, sample_asd, tmp_path):
        """No user-controlled JS variable should be interpolated into a query string."""
        html = _generate_chat_html(sample_asd, tmp_path)
        matches = _UNSAFE_INTERPOLATION.findall(html)
        assert matches == [], f"Found unsafe GraphQL interpolation: {matches}"

    def test_no_manual_quote_escaping_in_chat(self, sample_asd, tmp_path):
        """The old .replace(/\"/g, ...) workaround must not appear."""
        html = _generate_chat_html(sample_asd, tmp_path)
        matches = _MANUAL_ESCAPE.findall(html)
        assert matches == [], f"Found manual quote escaping: {matches}"

    def test_chat_query_uses_variables(self, sample_asd, tmp_path):
        """The chat ask query must declare $query as a GraphQL variable."""
        html = _generate_chat_html(sample_asd, tmp_path)
        assert "query AskAgent($query: String!)" in html

    def test_chat_gqlquery_accepts_variables(self, sample_asd, tmp_path):
        """The chat gqlQuery function must accept and forward a variables parameter."""
        html = _generate_chat_html(sample_asd, tmp_path)
        assert "async function gqlQuery(query, variables)" in html
        assert "JSON.stringify({ query, variables: variables || {} })" in html
