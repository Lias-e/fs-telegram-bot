import os

from src.config import get_env, load_selectors, load_settings


def test_load_settings():
    s = load_settings()
    assert "poll" in s
    assert "retry" in s
    assert "telegram" in s
    assert "browser" in s
    assert "logging" in s
    assert "database" in s


def test_load_selectors():
    s = load_selectors()
    assert "_meta" in s
    assert "notice_container" in s
    assert "title" in s
    assert "link" in s
    assert "date" in s


def test_get_env_default():
    assert get_env("NONEXISTENT_VAR_12345", "default_val") == "default_val"


def test_get_env_actual():
    os.environ["TEST_ENV_BOT"] = "test_value"
    assert get_env("TEST_ENV_BOT") == "test_value"
