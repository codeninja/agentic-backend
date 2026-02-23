"""Tests for the ninjastack CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from ninja_cli.cli import _validate_name, app
from typer.testing import CliRunner

runner = CliRunner()


def _init_project(root: Path) -> None:
    """Create a minimal .ninjastack/ directory for testing."""
    ns = root / ".ninjastack"
    ns.mkdir()
    ns.joinpath("schema.json").write_text(
        json.dumps(
            {
                "project_name": "test-project",
                "version": "1.0.0",
                "entities": [],
                "domains": [],
            }
        )
    )


class TestInitCommand:
    def test_init_creates_ninjastack_dir(self, tmp_path):
        result = runner.invoke(app, ["init", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Initialized" in result.output
        assert (tmp_path / ".ninjastack" / "schema.json").is_file()

    def test_init_custom_name(self, tmp_path):
        result = runner.invoke(app, ["init", "--name", "my-app", "--root", str(tmp_path)])
        assert result.exit_code == 0
        data = json.loads((tmp_path / ".ninjastack" / "schema.json").read_text())
        assert data["project_name"] == "my-app"

    def test_init_idempotent(self, tmp_path):
        runner.invoke(app, ["init", "--root", str(tmp_path)])
        result = runner.invoke(app, ["init", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestSyncCommand:
    def test_sync_not_initialized(self, tmp_path):
        result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.output.lower()

    @patch("ninja_codegen.engine.sync")
    def test_sync_generates_files(self, mock_sync, tmp_path):
        _init_project(tmp_path)
        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.generated_files = [Path("models.py"), Path("schema.py")]
        mock_result.file_count = 2
        mock_sync.return_value = mock_result

        result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Synced 2 file(s)" in result.output
        mock_sync.assert_called_once_with(root=tmp_path, force=False)

    @patch("ninja_codegen.engine.sync")
    def test_sync_skipped(self, mock_sync, tmp_path):
        _init_project(tmp_path)
        mock_result = MagicMock()
        mock_result.skipped = True
        mock_sync.return_value = mock_result

        result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "No changes" in result.output

    @patch("ninja_codegen.engine.sync")
    def test_sync_force(self, mock_sync, tmp_path):
        _init_project(tmp_path)
        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.generated_files = []
        mock_result.file_count = 0
        mock_sync.return_value = mock_result

        result = runner.invoke(app, ["sync", "--root", str(tmp_path), "--force"])
        assert result.exit_code == 0
        mock_sync.assert_called_once_with(root=tmp_path, force=True)


class TestServeCommand:
    def test_serve_no_schema(self, tmp_path, monkeypatch):
        """serve without a schema file should exit with error."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestDeployCommand:
    def test_deploy_not_initialized(self, tmp_path):
        result = runner.invoke(app, ["deploy", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.output.lower()

    @patch("ninja_deploy.k8s_generator.K8sGenerator")
    @patch("ninja_core.serialization.io.load_schema")
    def test_deploy_writes_manifests(self, mock_load, mock_gen_cls, tmp_path):
        _init_project(tmp_path)
        mock_schema = MagicMock()
        mock_load.return_value = mock_schema
        mock_gen = MagicMock()
        mock_gen.write_manifests.return_value = [Path("deployment.yaml"), Path("service.yaml")]
        mock_gen_cls.return_value = mock_gen

        result = runner.invoke(app, ["deploy", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Wrote 2 manifest(s)" in result.output
        mock_load.assert_called_once_with(tmp_path / ".ninjastack" / "schema.json")
        mock_gen_cls.assert_called_once_with(mock_schema)
        mock_gen.write_manifests.assert_called_once_with(tmp_path / "k8s")

    @patch("ninja_deploy.k8s_generator.K8sGenerator")
    @patch("ninja_core.serialization.io.load_schema")
    def test_deploy_custom_output_dir(self, mock_load, mock_gen_cls, tmp_path):
        _init_project(tmp_path)
        mock_load.return_value = MagicMock()
        mock_gen = MagicMock()
        mock_gen.write_manifests.return_value = []
        mock_gen_cls.return_value = mock_gen
        out = tmp_path / "custom-k8s"

        result = runner.invoke(app, ["deploy", "--root", str(tmp_path), "--output-dir", str(out)])
        assert result.exit_code == 0
        mock_gen.write_manifests.assert_called_once_with(out)


class TestValidateName:
    """Tests for _validate_name input sanitization (issue #54)."""

    @pytest.mark.parametrize(
        "name",
        [
            "ninja-foo",
            "a",
            "my-lib-2",
            "x123",
            "abc-def-ghi",
        ],
    )
    def test_valid_names_accepted(self, name):
        assert _validate_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",  # empty
            "Uppercase",  # uppercase letters
            "123start",  # starts with digit
            "-leading-hyphen",  # starts with hyphen
            "has spaces",  # spaces
            "semi;colon",  # shell metacharacter
            "pipe|char",  # shell metacharacter
            "back`tick",  # shell metacharacter
            "$(cmd)",  # command substitution
            "../traversal",  # path traversal
            "foo\nbar",  # newline injection
            "a" * 65,  # exceeds max length
            "ninja_underscore",  # underscores not allowed
            "has.dot",  # dots not allowed
        ],
    )
    def test_invalid_names_rejected(self, name):
        with pytest.raises(typer.BadParameter):
            _validate_name(name)

    def test_max_length_boundary(self):
        assert _validate_name("a" * 64) == "a" * 64
        with pytest.raises(typer.BadParameter):
            _validate_name("a" * 65)

    def test_create_lib_rejects_invalid_name(self, tmp_path, monkeypatch):
        """Integration test: invalid names are rejected before subprocess call."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "lib", "../etc/passwd"])
        assert result.exit_code != 0
        assert "Invalid name" in result.output

    def test_create_app_rejects_invalid_name(self, tmp_path, monkeypatch):
        """Integration test: invalid names are rejected before subprocess call."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "app", "$(rm -rf /)"])
        assert result.exit_code != 0
        assert "Invalid name" in result.output


def _mock_introspect_engine(mock_schema):
    """Create a mock IntrospectionEngine that returns mock_schema from run()."""
    mock_engine_cls = MagicMock()
    mock_engine = MagicMock()

    async def fake_run(conn_strs, **kw):
        return mock_schema

    mock_engine.run = fake_run
    mock_engine_cls.return_value = mock_engine
    return mock_engine_cls


def _make_schema(entities=None, relationships=None):
    """Build an AgenticSchema for testing."""
    from ninja_core.schema.project import AgenticSchema

    return AgenticSchema(
        project_name="untitled",
        entities=entities or [],
        relationships=relationships or [],
    )


def _make_entity(name, fields_spec):
    """Build an EntitySchema. fields_spec is list of (name, type, is_pk) tuples."""
    from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine

    fields = [
        FieldSchema(name=fname, field_type=getattr(FieldType, ftype), primary_key=pk)
        for fname, ftype, pk in fields_spec
    ]
    return EntitySchema(name=name, storage_engine=StorageEngine.SQL, fields=fields)


class TestIntrospectCommand:
    def test_introspect_json_output(self):
        schema = _make_schema(entities=[_make_entity("Users", [("id", "INTEGER", True), ("name", "STRING", False)])])
        mock_cls = _mock_introspect_engine(schema)

        with patch.dict(
            "sys.modules",
            {"ninja_introspect": MagicMock(), "ninja_introspect.engine": MagicMock(IntrospectionEngine=mock_cls)},
        ):
            result = runner.invoke(app, ["introspect", "sqlite:///test.db"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["project_name"] == "untitled"
        assert len(data["entities"]) == 1
        assert data["entities"][0]["name"] == "Users"

    def test_introspect_table_output(self):
        schema = _make_schema(entities=[_make_entity("Orders", [("id", "INTEGER", True), ("total", "FLOAT", False)])])
        mock_cls = _mock_introspect_engine(schema)

        with patch.dict(
            "sys.modules",
            {"ninja_introspect": MagicMock(), "ninja_introspect.engine": MagicMock(IntrospectionEngine=mock_cls)},
        ):
            result = runner.invoke(app, ["introspect", "sqlite:///test.db", "--format", "table"])

        assert result.exit_code == 0, result.output
        assert "Orders" in result.output
        assert "id, total" in result.output
        assert "Discovered 1 entity(ies)" in result.output

    def test_introspect_invalid_format(self):
        result = runner.invoke(app, ["introspect", "sqlite:///test.db", "--format", "xml"])
        assert result.exit_code == 1
        assert "Unknown format" in result.output

    def test_introspect_engine_error(self):
        mock_cls = MagicMock()
        mock_engine = MagicMock()

        async def fake_run(conn_strs, **kw):
            raise ValueError("Connection refused")

        mock_engine.run = fake_run
        mock_cls.return_value = mock_engine

        with patch.dict(
            "sys.modules",
            {"ninja_introspect": MagicMock(), "ninja_introspect.engine": MagicMock(IntrospectionEngine=mock_cls)},
        ):
            result = runner.invoke(app, ["introspect", "postgresql://bad/db"])

        assert result.exit_code == 1
        assert "Introspection failed" in result.output

    def test_introspect_with_relationships(self):
        from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType

        schema = _make_schema(
            entities=[
                _make_entity("Users", [("id", "INTEGER", True)]),
                _make_entity("Orders", [("id", "INTEGER", True), ("user_id", "INTEGER", False)]),
            ],
            relationships=[
                RelationshipSchema(
                    name="orders_user_id_fk",
                    source_entity="Orders",
                    target_entity="Users",
                    relationship_type=RelationshipType.HARD,
                    cardinality=Cardinality.MANY_TO_ONE,
                    source_field="user_id",
                    target_field="id",
                ),
            ],
        )
        mock_cls = _mock_introspect_engine(schema)

        with patch.dict(
            "sys.modules",
            {"ninja_introspect": MagicMock(), "ninja_introspect.engine": MagicMock(IntrospectionEngine=mock_cls)},
        ):
            result = runner.invoke(app, ["introspect", "sqlite:///test.db", "--format", "table"])

        assert result.exit_code == 0, result.output
        assert "Orders -> Users" in result.output
        assert "Relationships (1):" in result.output

    def test_introspect_missing_connection_string(self):
        result = runner.invoke(app, ["introspect"])
        assert result.exit_code != 0


class TestCreateCommands:
    def test_create_lib_missing_script(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "lib", "ninja-foo"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_create_app_missing_script(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(app, ["create", "app", "ninja-foo"])
        assert result.exit_code == 1
        assert "not found" in result.output
