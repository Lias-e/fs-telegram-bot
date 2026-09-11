import os

import pytest

from src.config import get_env, load_selectors, load_settings, validate_env


def test_load_settings():
    s = load_settings()
    assert "poll" in s
    assert "retry" in s
    assert "telegram" in s
    assert "browser" in s
    assert "logging" in s
    assert "database" in s
    assert s["database"]["path"].endswith("notices.db")
    assert "backup" in s["database"]["backup_dir"]


def test_load_selectors():
    s = load_selectors()
    assert "_meta" in s
    assert "link" in s
    assert "/annonces/" in s["link"]


def test_get_env_default():
    assert get_env("NONEXISTENT_VAR_12345", "default_val") == "default_val"


def test_get_env_actual():
    os.environ["TEST_ENV_BOT"] = "test_value"
    assert get_env("TEST_ENV_BOT") == "test_value"


def test_validate_env_requires_admin(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@ch")
    monkeypatch.delenv("ADMIN_TELEGRAM_ID", raising=False)
    with pytest.raises(RuntimeError, match="ADMIN_TELEGRAM_ID"):
        validate_env()


def test_validate_env_rejects_empty_admin(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@ch")
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "  ")
    with pytest.raises(RuntimeError, match="ADMIN_TELEGRAM_ID"):
        validate_env()


def test_validate_env_ok(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@ch")
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "12345")
    validate_env()
