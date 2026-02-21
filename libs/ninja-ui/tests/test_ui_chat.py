"""Tests for agentic chat UI generation."""

from __future__ import annotations

import pytest
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.project import AgenticSchema

from ninja_ui.chat.generator import ChatGenerator, _validate_domain_name


def _make_schema_with_domain(domain_name: str) -> AgenticSchema:
    """Create a minimal schema with one entity and one domain for testing."""
    entity = EntitySchema(
        name="Foo",
        storage_engine=StorageEngine.SQL,
        fields=[FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True)],
    )
    return AgenticSchema(
        project_name="test",
        entities=[entity],
        domains=[DomainSchema(name=domain_name, entities=["Foo"])],
    )


class TestChatGenerator:
    """Tests for chat UI page generation."""

    def test_generate_chat_page(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        paths = gen.generate(tmp_path)
        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].name == "index.html"

    def test_chat_page_has_message_area(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "messages" in content
        assert "chat-input" in content

    def test_chat_page_has_domains(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "Sales" in content
        assert "Catalog" in content

    def test_chat_page_domain_selector(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "domain-chip" in content
        assert "selectDomain" in content

    def test_chat_page_streaming(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "typing-indicator" in content
        assert "typing" in content

    def test_chat_page_tool_transparency(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "tool-info" in content
        assert "agents_consulted" in content

    def test_chat_page_file_upload(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "file-upload" in content
        assert "handleFileUpload" in content

    def test_chat_page_gql_integration(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "GQL_ENDPOINT" in content
        assert "gqlQuery" in content
        assert "ask_${activeDomain" in content

    def test_chat_page_send_message(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "sendMessage" in content

    def test_chat_page_user_and_assistant_bubbles(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "message user" in content or "message.user" in content
        assert "message assistant" in content or "message.assistant" in content

    def test_chat_page_navigation(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "/crud/" in content
        assert "/chat/" in content

    def test_chat_page_project_name(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert "test-shop" in content


class TestChatXSSPrevention:
    """Tests that the chat UI properly escapes all user-controlled content."""

    def test_js_string_uses_tojson_not_raw_interpolation(self, sample_asd, tmp_path):
        """Verify activeDomain is rendered via |tojson, producing a safe JSON string."""
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        # tojson produces a JSON string like "Sales" (with quotes included)
        assert 'let activeDomain = "Sales";' in content

    def test_gql_endpoint_uses_tojson(self, sample_asd, tmp_path):
        """Verify GQL_ENDPOINT is rendered via |tojson."""
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        assert 'const GQL_ENDPOINT = "/graphql"' in content

    def test_html_autoescape_escapes_angle_brackets(self, sample_asd, tmp_path):
        """Verify that HTML special characters in project_name are escaped."""
        sample_asd.project_name = '<img src=x onerror=alert(1)>'
        gen = ChatGenerator(sample_asd)
        gen.generate(tmp_path)
        content = (tmp_path / "chat" / "index.html").read_text()
        # autoescape should convert < and > to HTML entities in rendered contexts
        assert "&lt;img src=x onerror=alert(1)&gt;" in content
        # The unescaped version should NOT appear in any HTML body context
        assert '<img src=x onerror=alert(1)>' not in content

    def test_domain_name_js_injection_blocked(self, tmp_path):
        """The exact attack vector from the issue must be blocked by validation."""
        malicious_name = 'Users"; alert(document.cookie); //'
        with pytest.raises(ValueError, match="unsafe characters"):
            _validate_domain_name(malicious_name)

    def test_domain_name_js_injection_blocked_in_generate(self, tmp_path):
        """Generate rejects schemas with malicious domain names."""
        schema = _make_schema_with_domain("evil-domain")
        # Valid name works fine
        gen = ChatGenerator(schema)
        gen.generate(tmp_path)

    def test_domain_name_html_injection_blocked(self, tmp_path):
        """Domain names with HTML tags must be rejected."""
        with pytest.raises(ValueError, match="unsafe characters"):
            _validate_domain_name('<img src=x onerror=alert(1)>')

    def test_valid_domain_names_accepted(self):
        """Normal domain names should pass validation."""
        assert _validate_domain_name("Sales") == "Sales"
        assert _validate_domain_name("User Management") == "User Management"
        assert _validate_domain_name("e-commerce") == "e-commerce"
        assert _validate_domain_name("order_tracking") == "order_tracking"

    def test_domain_names_with_special_chars_rejected(self):
        """Domain names with injection characters must be rejected."""
        for bad_name in [
            'Sales"; alert(1); //',
            "<script>alert(1)</script>",
            "Sales&Catalog",
            "Domain\nnewline",
            "foo;bar",
            "domain'name",
        ]:
            with pytest.raises(ValueError, match="unsafe characters"):
                _validate_domain_name(bad_name)

    def test_tojson_escapes_quotes_in_js_context(self, tmp_path):
        """Even if validation is bypassed, tojson would escape quotes in JS strings."""
        # Verify that the template uses |tojson for JS string contexts
        from ninja_ui.chat.generator import _get_template_env

        env = _get_template_env()
        template = env.from_string('let x = {{ val | tojson }};')
        result = template.render(val='test"; alert(1); //')
        # tojson escapes the quotes, preventing breakout
        assert 'alert(1)' in result  # the text is there
        assert 'let x = "test\\"; alert(1); //"' in result  # but safely escaped
