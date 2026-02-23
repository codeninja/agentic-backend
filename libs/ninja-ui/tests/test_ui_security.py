"""Tests for UI template security — XSS prevention, injection safety, and CSP headers."""

from __future__ import annotations

import time
import urllib.request

import pytest
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.project import AgenticSchema
from ninja_ui.chat.generator import ChatGenerator
from ninja_ui.crud.generator import CrudGenerator
from ninja_ui.server import DEFAULT_CSP, UIServer
from ninja_ui.shared.sanitize import (
    is_safe_identifier,
    safe_identifier,
    safe_slug,
    sanitize_for_js_string,
)

# ---------------------------------------------------------------------------
# Sanitize module tests
# ---------------------------------------------------------------------------


class TestSafeIdentifier:
    """Tests for the safe_identifier function."""

    def test_clean_name_passes_through(self):
        assert safe_identifier("Customer") == "Customer"

    def test_underscored_name(self):
        assert safe_identifier("order_item") == "order_item"

    def test_hyphenated_name(self):
        assert safe_identifier("my-entity") == "my-entity"

    def test_strips_html_tags(self):
        result = safe_identifier('<script>alert("xss")</script>')
        assert "<" not in result
        assert ">" not in result
        assert "script" in result  # letters remain
        assert '"' not in result

    def test_strips_quotes(self):
        result = safe_identifier('name"onclick="alert(1)')
        assert '"' not in result
        assert "=" not in result
        assert "(" not in result

    def test_empty_after_sanitization_raises(self):
        with pytest.raises(ValueError, match="empty after sanitization"):
            safe_identifier("!@#$%^&*()")

    def test_numeric_prefix_preserved(self):
        result = safe_identifier("123field")
        assert result == "123field"


class TestSafeSlug:
    """Tests for the safe_slug function."""

    def test_lowercase(self):
        assert safe_slug("Customer") == "customer"

    def test_strips_dangerous_chars(self):
        result = safe_slug('<script>alert("xss")</script>')
        assert "<" not in result
        assert ">" not in result

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty after sanitization"):
            safe_slug("!@#$%^&*()")


class TestSanitizeForJsString:
    """Tests for JavaScript string literal escaping."""

    def test_plain_string(self):
        assert sanitize_for_js_string("hello") == "hello"

    def test_escapes_double_quotes(self):
        result = sanitize_for_js_string('say "hello"')
        assert '\\"' in result
        assert result == 'say \\"hello\\"'

    def test_escapes_single_quotes(self):
        result = sanitize_for_js_string("it's")
        assert "\\'" in result

    def test_escapes_backslashes(self):
        result = sanitize_for_js_string("path\\to\\file")
        assert "\\\\" in result

    def test_escapes_newlines(self):
        result = sanitize_for_js_string("line1\nline2")
        assert "\\n" in result
        assert "\n" not in result

    def test_escapes_angle_brackets(self):
        result = sanitize_for_js_string("<script>alert(1)</script>")
        assert "<" not in result
        assert ">" not in result
        assert "\\x3c" in result
        assert "\\x3e" in result

    def test_escapes_ampersand(self):
        result = sanitize_for_js_string("a & b")
        assert "&" not in result
        assert "\\x26" in result


class TestIsSafeIdentifier:
    """Tests for the is_safe_identifier check."""

    def test_valid_identifier(self):
        assert is_safe_identifier("Customer") is True

    def test_with_underscore(self):
        assert is_safe_identifier("order_item") is True

    def test_with_hyphen(self):
        assert is_safe_identifier("my-entity") is True

    def test_rejects_html(self):
        assert is_safe_identifier("<script>") is False

    def test_rejects_quotes(self):
        assert is_safe_identifier('name"') is False

    def test_rejects_spaces(self):
        assert is_safe_identifier("my entity") is False

    def test_rejects_empty(self):
        assert is_safe_identifier("") is False


# ---------------------------------------------------------------------------
# XSS entity name fixtures
# ---------------------------------------------------------------------------

XSS_ENTITY_NAME = '"><script>alert("xss")</script><span class="'
XSS_FIELD_NAME = '"><img src=x onerror=alert(1)>'
XSS_DOMAIN_NAME = '"><script>alert("domain")</script>'


def _xss_entity() -> EntitySchema:
    """Entity with a malicious name to test XSS prevention."""
    return EntitySchema(
        name=XSS_ENTITY_NAME,
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name=XSS_FIELD_NAME, field_type=FieldType.STRING),
        ],
    )


def _xss_schema() -> AgenticSchema:
    """ASD schema with malicious entity/domain names."""
    return AgenticSchema(
        project_name='<script>alert("project")</script>',
        entities=[_xss_entity()],
        relationships=[],
        domains=[
            DomainSchema(
                name=XSS_DOMAIN_NAME,
                description='<img src=x onerror=alert("desc")>',
                entities=[XSS_ENTITY_NAME],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# CRUD generator security tests
# ---------------------------------------------------------------------------


class TestCrudSecurityEscaping:
    """Verify CRUD generator escapes malicious schema names."""

    def test_entity_name_escaped_in_html(self, tmp_path):
        schema = _xss_schema()
        gen = CrudGenerator(schema)
        path = gen.generate_entity_page(_xss_entity(), tmp_path)
        content = path.read_text()
        # The raw XSS payload must not appear as executable JS
        assert 'alert("xss")' not in content
        # The entity name should be HTML-escaped
        assert "&lt;script&gt;" in content

    def test_entity_name_escaped_in_title(self, tmp_path):
        schema = _xss_schema()
        gen = CrudGenerator(schema)
        path = gen.generate_entity_page(_xss_entity(), tmp_path)
        content = path.read_text()
        # Should be HTML-escaped in the <title>
        assert "&lt;script&gt;" in content

    def test_field_name_escaped_in_html(self, tmp_path):
        schema = _xss_schema()
        gen = CrudGenerator(schema)
        path = gen.generate_entity_page(_xss_entity(), tmp_path)
        content = path.read_text()
        # The raw img/onerror XSS should not appear unescaped
        assert "<img src=x" not in content

    def test_index_page_escapes_names(self, tmp_path):
        schema = _xss_schema()
        gen = CrudGenerator(schema)
        path = gen.generate_index(tmp_path)
        content = path.read_text()
        # The project name XSS payload should be escaped
        assert 'alert("project")' not in content
        assert "&lt;script&gt;" in content

    def test_graphql_uses_variables_not_interpolation(self, tmp_path):
        """Verify generated JS uses parameterized GraphQL queries."""
        schema = _xss_schema()
        gen = CrudGenerator(schema)
        path = gen.generate_entity_page(_xss_entity(), tmp_path)
        content = path.read_text()
        # Should use variables pattern
        assert "variables" in content
        assert "$id" in content or "$limit" in content
        # Should NOT use naive string interpolation for user input
        assert 'replace(/"/g' not in content

    def test_no_inline_onclick_with_user_data(self, tmp_path):
        """Verify action buttons don't use inline onclick with dynamic values."""
        schema = _xss_schema()
        gen = CrudGenerator(schema)
        path = gen.generate_entity_page(_xss_entity(), tmp_path)
        content = path.read_text()
        # Should use data attributes and addEventListener instead of inline onclick
        assert "addEventListener" in content
        assert "dataset.pkval" in content

    def test_slug_sanitized_for_filename(self, tmp_path):
        """Verify the generated file has a safe filename."""
        schema = _xss_schema()
        gen = CrudGenerator(schema)
        path = gen.generate_entity_page(_xss_entity(), tmp_path)
        # Filename should only contain safe characters
        assert "<" not in path.name
        assert ">" not in path.name
        assert '"' not in path.name


# ---------------------------------------------------------------------------
# Chat generator security tests
# ---------------------------------------------------------------------------


class TestChatSecurityEscaping:
    """Verify Chat generator escapes malicious schema names."""

    def test_domain_name_escaped_in_html(self, tmp_path):
        schema = _xss_schema()
        gen = ChatGenerator(schema)
        paths = gen.generate(tmp_path)
        content = paths[0].read_text()
        # The XSS alert payload should not appear unescaped
        assert 'alert("domain")' not in content
        # The domain name should be HTML-escaped where displayed
        assert "&lt;script&gt;" in content

    def test_domain_description_escaped(self, tmp_path):
        schema = _xss_schema()
        gen = ChatGenerator(schema)
        paths = gen.generate(tmp_path)
        content = paths[0].read_text()
        # The raw onerror handler should not appear as an executable attribute
        # With autoescape, it becomes: &lt;img src=x onerror=alert(...)&gt;
        assert "<img src=x" not in content

    def test_chat_graphql_uses_variables(self, tmp_path):
        """Verify chat JS uses parameterized GraphQL queries."""
        schema = _xss_schema()
        gen = ChatGenerator(schema)
        paths = gen.generate(tmp_path)
        content = paths[0].read_text()
        assert "$query" in content
        assert 'replace(/"/g' not in content

    def test_chat_uses_textcontent_not_innerhtml(self, tmp_path):
        """Verify chat message rendering uses textContent, not innerHTML."""
        schema = _xss_schema()
        gen = ChatGenerator(schema)
        paths = gen.generate(tmp_path)
        content = paths[0].read_text()
        assert "textContent" in content
        # innerHTML should NOT be used for user message content
        assert "innerHTML" not in content

    def test_project_name_escaped(self, tmp_path):
        schema = _xss_schema()
        gen = ChatGenerator(schema)
        paths = gen.generate(tmp_path)
        content = paths[0].read_text()
        # The project name XSS should be escaped
        assert 'alert("project")' not in content
        assert "&lt;script&gt;" in content

    def test_domain_name_sanitized_in_js(self, tmp_path):
        """Verify domain name in JS variable is sanitized, not raw."""
        schema = _xss_schema()
        gen = ChatGenerator(schema)
        paths = gen.generate(tmp_path)
        content = paths[0].read_text()
        # The activeDomain JS variable should use the safe_id filtered value
        assert 'activeDomain = "scriptalertdomainscript"' in content


# ---------------------------------------------------------------------------
# Server CSP tests
# ---------------------------------------------------------------------------


class TestServerSecurityHeaders:
    """Verify the UI server sends Content-Security-Policy and other security headers."""

    def _make_server(self, tmp_path, port):
        """Helper to create a server with a test page."""
        index = tmp_path / "index.html"
        index.write_text("<!DOCTYPE html><html><body>Test</body></html>")
        return UIServer(tmp_path, port=port)

    def test_csp_header_present(self, tmp_path):
        server = self._make_server(tmp_path, 18850)
        server.start(background=True)
        try:
            time.sleep(0.3)
            resp = urllib.request.urlopen("http://127.0.0.1:18850/index.html")
            csp = resp.headers.get("Content-Security-Policy", "")
            assert "default-src" in csp
            assert "'self'" in csp
            assert "object-src 'none'" in csp
            assert "frame-ancestors 'none'" in csp
        finally:
            server.stop()

    def test_x_content_type_options(self, tmp_path):
        server = self._make_server(tmp_path, 18851)
        server.start(background=True)
        try:
            time.sleep(0.3)
            resp = urllib.request.urlopen("http://127.0.0.1:18851/index.html")
            assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        finally:
            server.stop()

    def test_x_frame_options(self, tmp_path):
        server = self._make_server(tmp_path, 18852)
        server.start(background=True)
        try:
            time.sleep(0.3)
            resp = urllib.request.urlopen("http://127.0.0.1:18852/index.html")
            assert resp.headers.get("X-Frame-Options") == "DENY"
        finally:
            server.stop()

    def test_referrer_policy(self, tmp_path):
        server = self._make_server(tmp_path, 18853)
        server.start(background=True)
        try:
            time.sleep(0.3)
            resp = urllib.request.urlopen("http://127.0.0.1:18853/index.html")
            assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        finally:
            server.stop()

    def test_default_csp_constant(self):
        """Verify the DEFAULT_CSP constant has all required directives."""
        assert "default-src 'self'" in DEFAULT_CSP
        assert "script-src" in DEFAULT_CSP
        assert "object-src 'none'" in DEFAULT_CSP
        assert "frame-ancestors 'none'" in DEFAULT_CSP
        assert "base-uri 'self'" in DEFAULT_CSP
        assert "form-action 'self'" in DEFAULT_CSP


# ---------------------------------------------------------------------------
# Normal generation still works (regression tests)
# ---------------------------------------------------------------------------


class TestSecurityRegressions:
    """Ensure security changes don't break normal generation."""

    def test_normal_entity_generates_correctly(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "Customer" in content
        assert 'ENTITY = "customer"' in content
        assert "data-table" in content

    def test_normal_chat_generates_correctly(self, sample_asd, tmp_path):
        gen = ChatGenerator(sample_asd)
        paths = gen.generate(tmp_path)
        content = paths[0].read_text()
        assert "Sales" in content
        assert "Catalog" in content
        assert "sendMessage" in content

    def test_normal_index_generates_correctly(self, sample_asd, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_index(tmp_path)
        content = path.read_text()
        assert "test-shop" in content
        assert "customer.html" in content
