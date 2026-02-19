def test_ninja_cli_imports():
    import ninja_cli

    assert ninja_cli is not None


def test_config_imports():
    from ninja_cli.config import AuthConfig, ConnectionProfile, ModelProvider, NinjaStackConfig

    assert NinjaStackConfig is not None
    assert ConnectionProfile is not None
    assert ModelProvider is not None
    assert AuthConfig is not None


def test_state_imports():
    from ninja_cli.state import init_state, is_initialized, load_config

    assert init_state is not None
    assert is_initialized is not None
    assert load_config is not None


def test_cli_imports():
    from ninja_cli.cli import app

    assert app is not None
