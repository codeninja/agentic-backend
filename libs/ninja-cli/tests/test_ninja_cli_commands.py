"""Tests for the ninjastack CLI commands."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from ninja_cli.cli import _validate_name, app
from typer.testing import CliRunner

runner = CliRunner()


def _init_project(tmp_path: Path, project_name: str = "test-project") -> None:
    """Helper: initialize a minimal .ninjastack/ directory."""
    ns = tmp_path / ".ninjastack"
    ns.mkdir()
    schema = {
        "version": "1.0",
        "project_name": project_name,
        "entities": [],
        "relationships": [],
        "domains": [],
    }
    (ns / "schema.json").write_text(json.dumps(schema, indent=2))
    (ns / "connections.json").write_text("[]")
    models = {"provider": "gemini", "model": "gemini-2.0-flash", "api_key_env": "GOOGLE_API_KEY"}
    (ns / "models.json").write_text(json.dumps(models))
    (ns / "auth.json").write_text(json.dumps({"strategy": "none", "issuer": None, "audience": None}))


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


class TestIntrospectCommand:
    def test_introspect_requires_init(self, tmp_path):
        result = runner.invoke(app, ["introspect", "-c", "postgresql://localhost/test", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "ninjastack init" in result.output

    @patch("ninja_cli.cli.load_config")
    def test_introspect_single_connection(self, mock_load_config, tmp_path):
        _init_project(tmp_path)
        mock_load_config.return_value = MagicMock(project_name="test-project")

        mock_schema = MagicMock()
        mock_schema.entities = [MagicMock(), MagicMock()]
        mock_schema.relationships = [MagicMock()]

        mock_engine_cls = MagicMock()
        mock_engine_instance = MagicMock()
        mock_engine_instance.run = AsyncMock(return_value=mock_schema)
        mock_engine_cls.return_value = mock_engine_instance

        modules = {
            "ninja_introspect": MagicMock(),
            "ninja_introspect.engine": MagicMock(
                IntrospectionEngine=mock_engine_cls,
            ),
        }
        with (
            patch.dict("sys.modules", modules),
            patch("ninja_core.serialization.io.save_schema") as mock_save,
        ):
            result = runner.invoke(
                app,
                [
                    "introspect",
                    "-c",
                    "postgresql://localhost/mydb",
                    "--root",
                    str(tmp_path),
                ],
            )
            assert result.exit_code == 0
            assert "Introspecting 1 connection(s)" in result.output
            assert "2 entities" in result.output
            assert "1 relationships" in result.output
            mock_save.assert_called_once()

    @patch("ninja_cli.cli.load_config")
    def test_introspect_multiple_connections(self, mock_load_config, tmp_path):
        _init_project(tmp_path)
        mock_load_config.return_value = MagicMock(project_name="test-project")

        mock_schema = MagicMock()
        mock_schema.entities = []
        mock_schema.relationships = []

        mock_engine_cls = MagicMock()
        mock_engine_instance = MagicMock()
        mock_engine_instance.run = AsyncMock(return_value=mock_schema)
        mock_engine_cls.return_value = mock_engine_instance

        modules = {
            "ninja_introspect": MagicMock(),
            "ninja_introspect.engine": MagicMock(
                IntrospectionEngine=mock_engine_cls,
            ),
        }
        with (
            patch.dict("sys.modules", modules),
            patch("ninja_core.serialization.io.save_schema"),
        ):
            result = runner.invoke(
                app,
                [
                    "introspect",
                    "-c",
                    "postgresql://localhost/mydb",
                    "-c",
                    "mongodb://localhost/docs",
                    "--root",
                    str(tmp_path),
                ],
            )
            assert result.exit_code == 0
            assert "Introspecting 2 connection(s)" in result.output

    @patch("ninja_cli.cli.load_config")
    def test_introspect_no_save(self, mock_load_config, tmp_path):
        _init_project(tmp_path)
        mock_load_config.return_value = MagicMock(project_name="test-project")

        mock_schema = MagicMock()
        mock_schema.entities = []
        mock_schema.relationships = []

        mock_engine_cls = MagicMock()
        mock_engine_instance = MagicMock()
        mock_engine_instance.run = AsyncMock(return_value=mock_schema)
        mock_engine_cls.return_value = mock_engine_instance

        modules = {
            "ninja_introspect": MagicMock(),
            "ninja_introspect.engine": MagicMock(
                IntrospectionEngine=mock_engine_cls,
            ),
        }
        with patch.dict("sys.modules", modules):
            result = runner.invoke(
                app,
                [
                    "introspect",
                    "-c",
                    "postgresql://localhost/mydb",
                    "--root",
                    str(tmp_path),
                    "--no-save",
                ],
            )
            assert result.exit_code == 0
            assert "not saved" in result.output

    @patch("ninja_cli.cli.load_config")
    def test_introspect_invalid_connection(self, mock_load_config, tmp_path):
        _init_project(tmp_path)
        mock_load_config.return_value = MagicMock(project_name="test-project")

        mock_engine_cls = MagicMock()
        mock_engine_instance = MagicMock()
        mock_engine_instance.run = AsyncMock(
            side_effect=ValueError("Cannot detect provider"),
        )
        mock_engine_cls.return_value = mock_engine_instance

        modules = {
            "ninja_introspect": MagicMock(),
            "ninja_introspect.engine": MagicMock(
                IntrospectionEngine=mock_engine_cls,
            ),
        }
        with patch.dict("sys.modules", modules):
            result = runner.invoke(
                app,
                [
                    "introspect",
                    "-c",
                    "invalid://bad",
                    "--root",
                    str(tmp_path),
                ],
            )
            assert result.exit_code == 1
            assert "Introspection failed" in result.output


class TestSyncCommand:
    def test_sync_requires_init(self, tmp_path):
        result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "ninjastack init" in result.output

    def test_sync_runs_codegen(self, tmp_path):
        _init_project(tmp_path)

        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.file_count = 3
        mock_result.generated_files = [
            Path("_generated/models/user.py"),
            Path("_generated/graphql/user.py"),
            Path("_generated/app.py"),
        ]

        with patch("ninja_codegen.engine.sync", return_value=mock_result) as mock_sync:
            result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
            assert result.exit_code == 0
            assert "Generated 3 file(s)" in result.output
            mock_sync.assert_called_once_with(root=tmp_path, output_dir=tmp_path, force=False)

    def test_sync_force_flag(self, tmp_path):
        _init_project(tmp_path)

        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.file_count = 1
        mock_result.generated_files = [Path("_generated/app.py")]

        with patch("ninja_codegen.engine.sync", return_value=mock_result) as mock_sync:
            result = runner.invoke(app, ["sync", "--root", str(tmp_path), "--force"])
            assert result.exit_code == 0
            mock_sync.assert_called_once_with(root=tmp_path, output_dir=tmp_path, force=True)

    def test_sync_no_changes(self, tmp_path):
        _init_project(tmp_path)

        mock_result = MagicMock()
        mock_result.skipped = True

        with patch("ninja_codegen.engine.sync", return_value=mock_result):
            result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
            assert result.exit_code == 0
            assert "No changes detected" in result.output

    def test_sync_custom_output(self, tmp_path):
        _init_project(tmp_path)
        out_dir = tmp_path / "custom_out"

        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.file_count = 1
        mock_result.generated_files = [Path("app.py")]

        with patch("ninja_codegen.engine.sync", return_value=mock_result) as mock_sync:
            result = runner.invoke(app, ["sync", "--root", str(tmp_path), "--output", str(out_dir)])
            assert result.exit_code == 0
            mock_sync.assert_called_once_with(root=tmp_path, output_dir=out_dir, force=False)

    def test_sync_missing_schema(self, tmp_path):
        _init_project(tmp_path)

        with patch("ninja_codegen.engine.sync", side_effect=FileNotFoundError("schema.json not found")):
            result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
            assert result.exit_code == 1
            assert "Sync failed" in result.output


class TestServeCommand:
    def test_serve_requires_init(self, tmp_path):
        result = runner.invoke(app, ["serve", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "ninjastack init" in result.output

    def test_serve_requires_generated_app(self, tmp_path):
        _init_project(tmp_path)
        result = runner.invoke(app, ["serve", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "ninjastack sync" in result.output

    def test_serve_launches_uvicorn(self, tmp_path):
        _init_project(tmp_path)
        gen_dir = tmp_path / "_generated"
        gen_dir.mkdir()
        (gen_dir / "app.py").write_text("app = None")

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            runner.invoke(app, ["serve", "--root", str(tmp_path)])
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "uvicorn" in cmd
            assert "_generated.app:app" in cmd
            assert "--host" in cmd
            assert "127.0.0.1" in cmd
            assert "--port" in cmd
            assert "8000" in cmd
            assert "--reload" in cmd

    def test_serve_custom_host_port(self, tmp_path):
        _init_project(tmp_path)
        gen_dir = tmp_path / "_generated"
        gen_dir.mkdir()
        (gen_dir / "app.py").write_text("app = None")

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            runner.invoke(
                app,
                [
                    "serve",
                    "--root",
                    str(tmp_path),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "9000",
                ],
            )
            cmd = mock_run.call_args[0][0]
            assert "0.0.0.0" in cmd
            assert "9000" in cmd

    def test_serve_no_reload(self, tmp_path):
        _init_project(tmp_path)
        gen_dir = tmp_path / "_generated"
        gen_dir.mkdir()
        (gen_dir / "app.py").write_text("app = None")

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            runner.invoke(app, ["serve", "--root", str(tmp_path), "--no-reload"])
            cmd = mock_run.call_args[0][0]
            assert "--reload" not in cmd


class TestDeployCommand:
    def test_deploy_requires_init(self, tmp_path):
        result = runner.invoke(app, ["deploy", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "ninjastack init" in result.output

    def test_deploy_k8s_default(self, tmp_path):
        _init_project(tmp_path)

        mock_gen = MagicMock()
        mock_gen.write_manifests.return_value = [Path("deployment.yaml"), Path("service.yaml")]

        with patch("ninja_deploy.k8s_generator.K8sGenerator", return_value=mock_gen):
            result = runner.invoke(app, ["deploy", "--root", str(tmp_path)])
            assert result.exit_code == 0
            assert "K8s manifests" in result.output
            assert "2 file(s)" in result.output

    def test_deploy_helm(self, tmp_path):
        _init_project(tmp_path)

        mock_gen = MagicMock()
        mock_gen.write_chart.return_value = [Path("Chart.yaml"), Path("values.yaml")]

        with patch("ninja_deploy.helm_generator.HelmGenerator", return_value=mock_gen):
            result = runner.invoke(app, ["deploy", "--root", str(tmp_path), "--format", "helm"])
            assert result.exit_code == 0
            assert "Helm chart" in result.output

    def test_deploy_docker(self, tmp_path):
        _init_project(tmp_path)

        mock_gen = MagicMock()
        mock_gen.write_dockerfiles.return_value = [Path("Dockerfile")]

        with patch("ninja_deploy.docker_generator.DockerGenerator", return_value=mock_gen):
            result = runner.invoke(app, ["deploy", "--root", str(tmp_path), "--format", "docker"])
            assert result.exit_code == 0
            assert "Dockerfiles" in result.output

    def test_deploy_all_formats(self, tmp_path):
        _init_project(tmp_path)

        mock_k8s = MagicMock()
        mock_k8s.write_manifests.return_value = [Path("deployment.yaml")]
        mock_helm = MagicMock()
        mock_helm.write_chart.return_value = [Path("Chart.yaml")]
        mock_docker = MagicMock()
        mock_docker.write_dockerfiles.return_value = [Path("Dockerfile")]

        with (
            patch("ninja_deploy.k8s_generator.K8sGenerator", return_value=mock_k8s),
            patch("ninja_deploy.helm_generator.HelmGenerator", return_value=mock_helm),
            patch("ninja_deploy.docker_generator.DockerGenerator", return_value=mock_docker),
        ):
            result = runner.invoke(app, ["deploy", "--root", str(tmp_path), "--format", "all"])
            assert result.exit_code == 0
            assert "K8s manifests" in result.output
            assert "Helm chart" in result.output
            assert "Dockerfiles" in result.output
            assert "Total: 3 deployment file(s)" in result.output

    def test_deploy_invalid_format(self, tmp_path):
        _init_project(tmp_path)
        result = runner.invoke(app, ["deploy", "--root", str(tmp_path), "--format", "invalid"])
        assert result.exit_code == 1
        assert "Invalid format" in result.output

    def test_deploy_custom_output(self, tmp_path):
        _init_project(tmp_path)
        out_dir = tmp_path / "my-manifests"

        mock_gen = MagicMock()
        mock_gen.write_manifests.return_value = [Path("deployment.yaml")]

        with patch("ninja_deploy.k8s_generator.K8sGenerator", return_value=mock_gen):
            result = runner.invoke(app, ["deploy", "--root", str(tmp_path), "--output", str(out_dir)])
            assert result.exit_code == 0
            mock_gen.write_manifests.assert_called_once_with(out_dir / "k8s")


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
