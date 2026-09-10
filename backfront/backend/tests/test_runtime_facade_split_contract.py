from __future__ import annotations

import importlib


def test_runtime_facade_modules_are_importable() -> None:
    for module_name in (
        "app.runtime.status_facade",
        "app.runtime.import_facade",
        "app.runtime.chat_facade",
        "app.runtime.logs_facade",
        "app.services.contact_llm.client",
        "app.services.contact_llm.prompt_builder",
        "app.services.contact_llm.history_repository",
        "app.services.contact_llm.progress_tracker",
        "app.services.contact_llm.response_parser",
        "app.services.telegram_sync.control",
        "app.services.telegram_sync.scheduler",
        "app.services.telegram_sync.worker_state",
        "app.services.telegram_sync.source_progress",
    ):
        assert importlib.import_module(module_name)


def test_owner_root_license_compose_template_is_available() -> None:
    module = importlib.import_module("x_files_root.owner_compose")
    assert "x-files-root-web" in module.ROOT_LICENSE_COMPOSE
    assert "x-files-license-server" in module.ROOT_LICENSE_COMPOSE
    assert "x-files-root-postgres" in module.ROOT_LICENSE_COMPOSE

