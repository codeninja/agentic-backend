"""Tests for the top-level UI generator orchestrator."""

from __future__ import annotations

from ninja_ui.generator import UIGenerationResult, UIGenerator


class TestUIGenerator:
    """Tests for the UIGenerator orchestrator."""

    def test_generate_all(self, sample_asd, tmp_path):
        gen = UIGenerator(sample_asd)
        result = gen.generate(tmp_path)
        assert isinstance(result, UIGenerationResult)
        # 4 CRUD (index + 3 entities) + 1 chat
        assert len(result.generated_files) == 5
        assert all(f.exists() for f in result.generated_files)

    def test_crud_dir_set(self, sample_asd, tmp_path):
        gen = UIGenerator(sample_asd)
        result = gen.generate(tmp_path)
        assert result.crud_dir == tmp_path / "crud"
        assert result.crud_dir.is_dir()

    def test_chat_dir_set(self, sample_asd, tmp_path):
        gen = UIGenerator(sample_asd)
        result = gen.generate(tmp_path)
        assert result.chat_dir == tmp_path / "chat"
        assert result.chat_dir.is_dir()

    def test_generate_crud_only(self, sample_asd, tmp_path):
        gen = UIGenerator(sample_asd)
        result = gen.generate_crud_only(tmp_path)
        assert result.crud_dir is not None
        assert result.chat_dir is None
        assert len(result.generated_files) == 4

    def test_generate_chat_only(self, sample_asd, tmp_path):
        gen = UIGenerator(sample_asd)
        result = gen.generate_chat_only(tmp_path)
        assert result.chat_dir is not None
        assert result.crud_dir is None
        assert len(result.generated_files) == 1

    def test_idempotent_generation(self, sample_asd, tmp_path):
        gen = UIGenerator(sample_asd)
        result1 = gen.generate(tmp_path)
        result2 = gen.generate(tmp_path)
        assert len(result1.generated_files) == len(result2.generated_files)
        for f in result2.generated_files:
            assert f.exists()

    def test_generated_html_valid_structure(self, sample_asd, tmp_path):
        gen = UIGenerator(sample_asd)
        result = gen.generate(tmp_path)
        for f in result.generated_files:
            content = f.read_text()
            assert "<!DOCTYPE html>" in content
            assert "<html" in content
            assert "</html>" in content
