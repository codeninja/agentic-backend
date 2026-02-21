"""Tests for agentic chat UI generation."""

from __future__ import annotations

from ninja_ui.chat.generator import ChatGenerator


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
        assert "ask_${domainKey}" in content

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
