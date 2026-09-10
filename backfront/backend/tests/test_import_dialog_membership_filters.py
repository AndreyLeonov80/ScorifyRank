from app.schemas.compat_models import TelegramDialogDTO
from app.services import channels
from app.services import telegram_sources_runtime
import back
import app.legacy_runtime as legacy_runtime


def _dialog(selector: str, *, added: bool = False) -> TelegramDialogDTO:
    return TelegramDialogDTO(
        id=abs(hash(selector)) % 1_000_000,
        title=selector,
        selector=selector,
        username=selector if not selector.isdigit() else None,
        chat_type="group",
        is_already_added=added,
    )


def test_all_filter_does_not_inject_added_fallback_rows(monkeypatch):
    monkeypatch.setattr(
        telegram_sources_runtime,
        "_source_selectors_as_strings",
        lambda: ["added_chat", "missing_added"],
        raising=False,
    )
    monkeypatch.setattr(
        telegram_sources_runtime,
        "_selector_identity",
        lambda value: str(value or "").strip().lstrip("@").lower(),
        raising=False,
    )
    monkeypatch.setattr(
        telegram_sources_runtime,
        "_normalize_source_selector",
        lambda value: str(value or "").strip(),
        raising=False,
    )
    monkeypatch.setattr(telegram_sources_runtime, "_get_app_settings", lambda: {}, raising=False)
    monkeypatch.setattr(telegram_sources_runtime, "_xfiles_import_history_months_max", lambda: 0, raising=False)
    monkeypatch.setattr(telegram_sources_runtime, "_xfiles_import_message_limit_max", lambda: 0, raising=False)
    monkeypatch.setattr(telegram_sources_runtime, "_import_dialog_settings_state", lambda: {}, raising=False)
    monkeypatch.setattr(
        telegram_sources_runtime,
        "_effective_import_limits_for_selector",
        lambda selector: {
            "import_history_months": 0,
            "import_message_limit": 0,
            "import_max_history_months": 0,
            "import_max_message_limit": 0,
        },
        raising=False,
    )

    dialogs = [_dialog("added_chat"), _dialog("not_added_chat")]

    all_rows = telegram_sources_runtime._merge_added_source_selectors_into_dialogs(
        dialogs,
        include_missing_added=False,
    )
    added_rows = telegram_sources_runtime._merge_added_source_selectors_into_dialogs(
        dialogs,
        include_missing_added=True,
    )

    assert [row.selector for row in all_rows] == ["added_chat", "not_added_chat"]
    assert all_rows[0].is_already_added is True
    assert all_rows[1].is_already_added is False
    assert "missing_added" in {row.selector for row in added_rows}


def test_dialog_membership_filters_large_catalog(monkeypatch):
    added = {f"dialog_{idx}" for idx in range(0, 1200, 10)}
    dialogs = [_dialog(f"dialog_{idx}", added=False) for idx in range(1200)]

    async def fake_dialogs(*, force_refresh=False):
        return list(dialogs)

    monkeypatch.setattr(channels, "_get_telegram_dialogs_for_api", fake_dialogs, raising=False)
    def mark_membership(items, *, include_missing_added=True):
        for item in items:
            item.is_already_added = str(item.selector or "").strip().lower() in added
        return list(items)

    monkeypatch.setattr(channels, "_merge_added_source_selectors_into_dialogs", mark_membership, raising=False)
    monkeypatch.setattr(channels, "_source_selectors_as_strings", lambda: sorted(added), raising=False)
    monkeypatch.setattr(back, "_source_selectors_as_strings", lambda: sorted(added), raising=False)
    monkeypatch.setattr(legacy_runtime, "_source_selectors_as_strings", lambda: sorted(added), raising=False)
    monkeypatch.setattr(channels, "_selector_identity", lambda value: str(value or "").strip().lower(), raising=False)
    monkeypatch.setattr(back, "_selector_identity", lambda value: str(value or "").strip().lower(), raising=False)
    monkeypatch.setattr(legacy_runtime, "_selector_identity", lambda value: str(value or "").strip().lower(), raising=False)
    monkeypatch.setattr(
        channels,
        "_dialog_identity_values",
        lambda dialog: {str(dialog.selector or "").strip().lower(), str(dialog.username or "").strip().lower(), str(dialog.title or "").strip().lower()},
        raising=False,
    )
    monkeypatch.setattr(
        back,
        "_dialog_identity_values",
        lambda dialog: {str(dialog.selector or "").strip().lower(), str(dialog.username or "").strip().lower(), str(dialog.title or "").strip().lower()},
        raising=False,
    )
    monkeypatch.setattr(
        legacy_runtime,
        "_dialog_identity_values",
        lambda dialog: {str(dialog.selector or "").strip().lower(), str(dialog.username or "").strip().lower(), str(dialog.title or "").strip().lower()},
        raising=False,
    )
    monkeypatch.setattr(channels, "_normalize_source_selector", lambda value: str(value or "").strip(), raising=False)
    monkeypatch.setattr(channels, "_get_app_settings", lambda: {}, raising=False)
    monkeypatch.setattr(channels, "_xfiles_import_history_months_max", lambda: 0, raising=False)
    monkeypatch.setattr(channels, "_xfiles_import_message_limit_max", lambda: 0, raising=False)
    monkeypatch.setattr(channels, "_import_dialog_settings_state", lambda: {}, raising=False)
    monkeypatch.setattr(
        channels,
        "_effective_import_limits_from_cached_state",
        lambda *args, **kwargs: {
            "import_history_months": 0,
            "import_message_limit": 0,
            "import_max_history_months": 0,
            "import_max_message_limit": 0,
        },
        raising=False,
    )

    import asyncio

    all_page = asyncio.run(channels.api_payme_telegram_dialogs(page=1, page_size=2000, query="", membership_filter="all"))
    added_page = asyncio.run(channels.api_payme_telegram_dialogs(page=1, page_size=2000, query="", membership_filter="added"))
    not_added_page = asyncio.run(channels.api_payme_telegram_dialogs(page=1, page_size=2000, query="", membership_filter="not_added"))

    assert all_page.total == 1200
    assert added_page.total == len(added)
    assert not_added_page.total == 1200 - len(added)
    assert all(item.is_already_added for item in added_page.items)
    assert all(not item.is_already_added for item in not_added_page.items)
