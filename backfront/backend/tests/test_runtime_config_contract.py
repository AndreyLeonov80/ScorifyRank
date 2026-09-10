from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_config_defaults_have_single_owner() -> None:
    app_settings = (ROOT / "app/core/app_settings.py").read_text(encoding="utf-8")
    config_service = (ROOT / "app/services/config.py").read_text(encoding="utf-8")
    legacy_runtime = (ROOT / "app/legacy_runtime.py").read_text(encoding="utf-8")

    assert "def _default_app_settings()" in app_settings
    assert "def _default_app_settings()" not in config_service
    assert "def _default_app_settings()" not in legacy_runtime
    for key in (
        "telegram_api_id",
        "telegram_api_hash",
        "openrouter_api_key",
        "import_default_message_limit",
        "telegram_unlimited_import_enabled",
    ):
        assert key in app_settings
        assert config_service.count(key) <= 2
