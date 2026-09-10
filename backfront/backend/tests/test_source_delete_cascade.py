from __future__ import annotations

import asyncio

from app.schemas.compat_models import SourceSelectorPayload
from app.services import channels


def test_source_remove_cascades_state_cache_dialogs_purge_and_sync(monkeypatch):
    calls = {
        "write_selectors": [],
        "cache_prefix": [],
        "dialog_removed": [],
        "purged": [],
        "remembered": [],
        "save_state": 0,
        "source_reload": 0,
        "ensure_job": [],
    }

    monkeypatch.setattr(channels, "_normalize_source_selector", lambda value: str(value or "").strip(), raising=False)
    monkeypatch.setattr(channels, "_selector_identity", lambda value: str(value or "").strip().lstrip("@").lower(), raising=False)
    monkeypatch.setattr(channels, "_source_selectors_as_strings", lambda: ["breakfast_with_harskii", "noirser"], raising=False)
    monkeypatch.setattr(channels, "_load_source_selectors_for_ui", lambda: ["noirser"], raising=False)
    monkeypatch.setattr(channels, "_write_source_selectors", lambda selectors: calls["write_selectors"].append(list(selectors)), raising=False)
    monkeypatch.setattr(channels, "_api_snapshot_cache_clear_prefix", lambda prefix: calls["cache_prefix"].append(prefix), raising=False)
    monkeypatch.setattr(channels, "_lead_snapshot_cache", {"items": ["stale"], "updated_at": 123.0}, raising=False)
    monkeypatch.setattr(channels, "_mark_telegram_dialogs_cache_removed", lambda selectors: calls["dialog_removed"].append(list(selectors)), raising=False)
    monkeypatch.setattr(channels, "_purge_removed_source_data", lambda selector: calls["purged"].append(selector) or {"total_removed": 7}, raising=False)
    monkeypatch.setattr(channels, "_remember_selector", lambda selector: calls["remembered"].append(selector), raising=False)
    monkeypatch.setattr(channels.telegram_sync, "save_state", lambda: calls.__setitem__("save_state", calls["save_state"] + 1), raising=False)
    monkeypatch.setattr(channels.telegram_sync, "request_source_reload", lambda: calls.__setitem__("source_reload", calls["source_reload"] + 1), raising=False)
    monkeypatch.setattr(channels, "_schedule_telegram_sync_start", lambda: None, raising=False)
    monkeypatch.setattr(channels, "_ensure_telegram_sync_worker_job", lambda reason: calls["ensure_job"].append(reason), raising=False)

    result = asyncio.run(
        channels.api_payme_source_remove(SourceSelectorPayload(selector="breakfast_with_harskii"))
    )

    assert result.ok is True
    assert result.selected == ["noirser"]
    assert result.purge == {"total_removed": 7}
    assert calls["write_selectors"] == [["noirser"]]
    assert calls["cache_prefix"] == ["leads:", "dashboard_summary:"]
    assert channels._lead_snapshot_cache["items"] is None
    assert channels._lead_snapshot_cache["updated_at"] == 0.0
    assert calls["dialog_removed"] == [["breakfast_with_harskii"]]
    assert calls["purged"] == ["breakfast_with_harskii"]
    assert calls["remembered"] == ["breakfast_with_harskii"]
    assert calls["save_state"] == 1
    assert calls["source_reload"] == 1
    assert calls["ensure_job"] == ["source-remove"]
