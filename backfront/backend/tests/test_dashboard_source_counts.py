from __future__ import annotations

from datetime import datetime, timezone

from app.services.dashboard_source_stats import build_dashboard_scanned_sources_payload


class _TelegramSyncStub:
    _chat_backfill_tasks = {}
    _chat_setup_tasks = {}

    def get_sync_control_status(self):
        return {"paused": False}

    def _selector_key(self, selector):
        return str(selector or "").strip().lower()


def test_dashboard_scanned_sources_uses_selected_sources_as_truth() -> None:
    payload = build_dashboard_scanned_sources_payload(
        lead_items=[],
        dialog_items=[],
        telegram_flood_wait={},
        telegram_rate_limits={},
        limit=10,
        source_selectors=["selected_a", "selected_b"],
        import_sync_selectors=[f"queued_{idx}" for idx in range(1200)],
        telegram_sync=_TelegramSyncStub(),
        selector_to_lead_name=lambda value: str(value or "").strip().lower(),
        lead_scan_group_fields=lambda *_args: {"scan_group": "C"},
        telegram_chat_state_for_lead=lambda *_args: {},
        utc_now=lambda: datetime(2026, 5, 24, tzinfo=timezone.utc),
    )

    assert payload["total"] == 2
    assert payload["totals"]["selected_sources"] == 2
    assert payload["totals"]["import_sync_queued_sources"] == 1200
    assert [item["selector"] for item in payload["items"]] == ["selected_a", "selected_b"]
