from __future__ import annotations

import asyncio

from app.services import contact_llm_runtime
from app.services import channels, config
from app.services import leads
from app.schemas.compat_models import LeadGroupPayload, TelegramDialogSettingsPayload


class FakeTelegramSync:
    def __init__(self):
        self.state = {}
        self.saved = 0
        self.reloads = 0

    def save_state(self):
        self.saved += 1

    def request_source_reload(self):
        self.reloads += 1


def test_personal_import_limit_persists_and_wakes_sync(monkeypatch):
    calls = {
        "set_limits": [],
        "cache_prefix": [],
        "source_reload": 0,
        "schedule_start": 0,
        "ensure_job": [],
    }

    monkeypatch.setattr(channels, "_normalize_source_selector", lambda value: str(value or "").strip(), raising=False)

    def fake_set_limits(selector, *, import_history_months, import_message_limit):
        calls["set_limits"].append((selector, import_history_months, import_message_limit))
        return {
            "import_history_months": import_history_months,
            "import_message_limit": import_message_limit,
            "import_max_history_months": 0,
            "import_max_message_limit": 0,
        }

    monkeypatch.setattr(channels, "_set_import_limits_for_selector", fake_set_limits, raising=False)
    monkeypatch.setattr(channels, "_api_snapshot_cache_clear_prefix", lambda prefix: calls["cache_prefix"].append(prefix), raising=False)
    monkeypatch.setattr(channels, "_lead_snapshot_cache", {"items": ["stale"], "updated_at": 123.0}, raising=False)
    monkeypatch.setattr(channels.telegram_sync, "request_source_reload", lambda: calls.__setitem__("source_reload", calls["source_reload"] + 1), raising=False)
    monkeypatch.setattr(channels, "_schedule_telegram_sync_start", lambda: calls.__setitem__("schedule_start", calls["schedule_start"] + 1), raising=False)
    monkeypatch.setattr(channels, "_ensure_telegram_sync_worker_job", lambda reason: calls["ensure_job"].append(reason), raising=False)

    result = asyncio.run(
        channels.api_payme_telegram_dialogs_settings(
            TelegramDialogSettingsPayload(
                selector="breakfast_with_harskii",
                import_history_months=2,
                import_message_limit=2000,
            )
        )
    )

    assert result.ok is True
    assert result.selector == "breakfast_with_harskii"
    assert result.import_history_months == 2
    assert result.import_message_limit == 2000
    assert calls["set_limits"] == [("breakfast_with_harskii", 2, 2000)]
    assert "leads:" in calls["cache_prefix"]
    assert channels._lead_snapshot_cache["items"] is None
    assert calls["source_reload"] == 1
    assert calls["schedule_start"] == 1
    assert calls["ensure_job"] == ["dialog-import-settings"]


def test_source_limit_persistence_full_grid(monkeypatch):
    sync = FakeTelegramSync()
    monkeypatch.setattr(contact_llm_runtime, "telegram_sync", sync, raising=False)
    monkeypatch.setattr(contact_llm_runtime, "_normalize_source_selector", lambda value: str(value or "").strip().lstrip("@"), raising=False)
    monkeypatch.setattr(contact_llm_runtime, "_selector_identity", lambda value: str(value or "").strip().lstrip("@").lower(), raising=False)
    monkeypatch.setattr(contact_llm_runtime, "_remember_selector", lambda _value: None, raising=False)
    monkeypatch.setattr(
        contact_llm_runtime,
        "_import_dialog_settings_state",
        lambda: sync.state.setdefault("_import_dialog_settings", {}),
        raising=False,
    )
    monkeypatch.setattr(contact_llm_runtime, "_xfiles_import_history_months_max", lambda: 1200, raising=False)
    monkeypatch.setattr(contact_llm_runtime, "_xfiles_import_message_limit_max", lambda: 100000000, raising=False)

    personal = contact_llm_runtime._set_import_limits_for_selector.__wrapped__(
        "@breakfast_with_harskii",
        import_history_months=2,
        import_message_limit=2000,
    )

    assert personal["import_history_months"] == 2
    assert personal["import_message_limit"] == 2000
    assert sync.state["_import_dialog_settings"]["breakfast_with_harskii"] == {
        "import_history_months": 2,
        "import_message_limit": 2000,
    }
    assert sync.saved == 1

    saved_settings = {}
    monkeypatch.setattr(
        contact_llm_runtime,
        "_source_selectors_as_strings",
        lambda: ["@breakfast_with_harskii", "@noirser", "numeric_2308654471"],
        raising=False,
    )
    monkeypatch.setattr(
        contact_llm_runtime,
        "_get_app_settings",
        lambda: {"import_default_history_months": 1, "import_default_message_limit": 1000},
        raising=False,
    )
    monkeypatch.setattr(
        contact_llm_runtime,
        "_save_app_settings",
        lambda settings: saved_settings.update(settings) or settings,
        raising=False,
    )
    monkeypatch.setattr(
        contact_llm_runtime,
        "_bulk_set_import_limits_for_selectors",
        contact_llm_runtime._bulk_set_import_limits_for_selectors.__wrapped__,
        raising=False,
    )

    bulk = contact_llm_runtime._apply_import_limits_for_all_selected_sources.__wrapped__(
        import_history_months=3,
        import_message_limit=3000,
        unlimited=False,
    )

    assert bulk["updated_sources_count"] == 3
    assert sync.state["_import_dialog_settings"]["breakfast_with_harskii"]["import_message_limit"] == 3000
    assert sync.state["_import_dialog_settings"]["noirser"]["import_history_months"] == 3
    assert sync.state["_import_dialog_settings"]["numeric_2308654471"]["import_message_limit"] == 3000
    assert saved_settings["telegram_unlimited_import_enabled"] is False


def test_bulk_import_limits_apply_to_all_and_invalidate_source_views(monkeypatch):
    calls = {
        "apply_all": [],
        "cache_prefix": [],
        "ensure_job": [],
    }

    def fake_apply_all(*, import_history_months, import_message_limit, unlimited):
        calls["apply_all"].append((import_history_months, import_message_limit, unlimited))
        return {"ok": True, "updated": 81}

    monkeypatch.setattr(config, "_apply_import_limits_for_all_selected_sources", fake_apply_all, raising=False)
    monkeypatch.setattr(config, "_api_snapshot_cache_clear_prefix", lambda prefix: calls["cache_prefix"].append(prefix), raising=False)
    monkeypatch.setattr(config, "_lead_snapshot_cache", {"items": ["stale"], "updated_at": 123.0}, raising=False)
    monkeypatch.setattr(config, "_ensure_telegram_sync_job_after_import_limits", lambda reason: calls["ensure_job"].append(reason), raising=False)
    monkeypatch.setattr(config, "_get_app_settings", lambda: {"import_default_history_months": 2, "import_default_message_limit": 2000}, raising=False)

    result = config.api_payme_settings_apply_import_limits_all(
        {"unlimited": False, "import_history_months": 2, "import_message_limit": 2000}
    )

    assert result["ok"] is True
    assert result["updated"] == 81
    assert calls["apply_all"] == [(2, 2000, False)]
    assert "leads:" in calls["cache_prefix"]
    assert "dashboard_summary:" in calls["cache_prefix"]
    assert config._lead_snapshot_cache["items"] is None
    assert config._lead_snapshot_cache["updated_at"] == 0.0
    assert calls["ensure_job"] == ["import-limits-all"]


def test_source_group_persistence(monkeypatch):
    settings = {
        "telegram_scan_groups": [
            {"id": "A", "label": "A — критичные продажи/лиды", "frequency": "live", "interval_minutes": 0},
            {"id": "C", "label": "C — фоновые", "frequency": "1-4 раза в день", "interval_minutes": 360},
        ],
        "telegram_scan_group_assignments": {},
    }
    saved_settings = {}
    sync = FakeTelegramSync()

    monkeypatch.setattr(leads, "_get_app_settings", lambda: dict(settings), raising=False)

    def fake_save_app_settings(payload):
        saved_settings.clear()
        saved_settings.update(payload)
        settings.update(payload)
        return payload

    monkeypatch.setattr(leads, "_save_app_settings", fake_save_app_settings, raising=False)
    monkeypatch.setattr(leads, "telegram_sync", sync, raising=False)
    monkeypatch.setattr(leads, "_api_snapshot_cache_clear_prefix", lambda _prefix: None, raising=False)
    monkeypatch.setattr(leads, "_lead_snapshot_cache", {"items": ["stale"], "updated_at": 123.0}, raising=False)
    monkeypatch.setattr(
        leads,
        "_lead_scan_group_fields",
        lambda _lead, _selector=None: {
            "scan_group": settings["telegram_scan_group_assignments"].get("breakfast_with_harskii", "C"),
            "scan_group_label": "A — критичные продажи/лиды",
            "scan_group_frequency": "live",
            "scan_group_interval_minutes": None,
        },
        raising=False,
    )

    result = asyncio.run(
        leads.api_payme_leads_group(
            LeadGroupPayload(
                lead="breakfast_with_harskii",
                selector="@breakfast_with_harskii",
                scan_group="A",
            )
        )
    )

    assignments = saved_settings["telegram_scan_group_assignments"]
    assert result.ok is True
    assert result.scan_group == "A"
    assert assignments["breakfast_with_harskii"] == "A"
    assert sync.saved == 1
    assert sync.reloads == 1
