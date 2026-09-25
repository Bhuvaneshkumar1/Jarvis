import os
import pytest
from config.settings import Settings, get_settings
from jarvis.core.exceptions import ConfigurationError


def test_config_loading_success(temp_dir):
    env_path = os.path.join(temp_dir, ".env.test")
    with open(env_path, "w") as f:
        f.write("JARVIS_ENV=test\nPORT=6000\nJARVIS_MAX_MEMORY_MB=4096\n")

    settings = Settings(env_file=env_path)
    assert settings.env == "test"
    assert settings.port == 6000
    assert settings.max_memory_mb == 4096


def test_config_sanitized_summary():
    settings = get_settings()
    summary = settings.get_sanitized_summary()
    assert "env" in summary
    assert "port" in summary
    # Ensure no raw secret values are returned in summary keys
    for k, v in summary.items():
        assert not str(v).startswith("sk-")
        assert not str(v).startswith("ghp_")


def test_negative_malformed_port(temp_dir):
    env_path = os.path.join(temp_dir, ".env.badport")
    with open(env_path, "w") as f:
        f.write("PORT=not_an_int\n")

    with pytest.raises(ConfigurationError) as exc_info:
        Settings(env_file=env_path)
    assert "Invalid PORT value" in str(exc_info.value)


def test_negative_invalid_memory_threshold(temp_dir):
    env_path = os.path.join(temp_dir, ".env.badmem")
    with open(env_path, "w") as f:
        f.write("PORT=5000\nJARVIS_MAX_MEMORY_MB=128\n")

    with pytest.raises(ConfigurationError) as exc_info:
        Settings(env_file=env_path)
    assert "below minimum threshold" in str(exc_info.value)
