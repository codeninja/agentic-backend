"""Tests for UI template security — GraphQL variables and autoescape."""

from __future__ import annotations

from ninja_ui.chat.generator import ChatGenerator
from ninja_ui.crud.generator import CrudGenerator, _get_template_env
from ninja_ui.chat.generator import _get_template_env as _chat_get_template_env


class TestCrudTemplateVariables:
    """Tests that CRUD templates use GraphQL variables instead of string interpolation."""

    def test_create_uses_variables(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "$input: JSON!" in content
        assert "variables:" in content or "variables ||" in content

    def test_update_uses_variables(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "$id: String!" in content
        assert "$patch: JSON!" in content

    def test_delete_uses_variables(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert 'mutation DeleteEntity($id: String!)' in content

    def test_list_uses_variables(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "$limit: Int!" in content
        assert "$offset: Int!" in content

    def test_search_uses_variables(self, sample_asd, product_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(product_entity, tmp_path)
        content = path.read_text()
        assert "$query: String!" in content

    def test_no_string_interpolation_in_mutations(self, sample_asd, customer_entity, tmp_path):
        """Ensure no direct string interpolation of user values in query strings."""
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        # The old pattern was: create_${ENTITY}(input: "${inputJson}")
        assert 'input: "${' not in content
        assert 'patch: "${' not in content
        assert 'id: "${' not in content

    def test_csrf_header_in_fetch(self, sample_asd, customer_entity, tmp_path):
        """Generated JS includes X-Requested-With header for CSRF protection."""
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "X-Requested-With" in content


class TestChatTemplateVariables:
    """Tests that chat templates use GraphQL variables."""

    def test_ask_uses_variables(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "$query: String!" in content

    def test_no_string_interpolation_in_query(self, sample_asd, tmp_path):
        """Ensure no direct string interpolation of user text in query strings."""
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        # The old pattern was: (query: "${text.replace(...)}")
        assert 'query: "${' not in content
        assert '.replace(/"/g' not in content

    def test_csrf_header_in_fetch(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "X-Requested-With" in content


class TestAutoescapeEnabled:
    """Tests that Jinja2 autoescape is enabled in both generators."""

    def test_crud_autoescape_enabled(self):
        env = _get_template_env()
        assert env.autoescape is True

    def test_chat_autoescape_enabled(self):
        env = _chat_get_template_env()
        assert env.autoescape is True
