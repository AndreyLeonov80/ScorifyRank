import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.services import telegram_sync_runtime
from app.services.telegram_sync.backfill import backfill_stop_reason, build_backfill_limits
from app.services.telegram_sync.rate_limits import flood_wait_seconds, rate_limit_state
from app.services.telegram_sync.state import existing_jsonl_message_bounds


class FakeClient:
    def __init__(self, entity):
        self.entity = entity
        self.selector = None

    async def get_entity(self, selector):
        self.selector = selector
        return self.entity


class FakeEntity:
    id = 123
    access_hash = 456
    username = "Breakfast_With_Harskii"
    title = "Breakfast"


class TelegramSyncRuntimeSplitTest(unittest.TestCase):
    def test_load_selected_chats_normalizes_state_items(self) -> None:
        telegram_sync_runtime.SOURCE_SELECTORS_STATE_KEY = "_source_selectors"
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync.state = {"_source_selectors": [" 123 ", "@Channel", "", None, "  @Group  "]}

        self.assertEqual(sync._load_selected_chats(), [123, "@Channel", "@Group"])

    def test_resolve_entity_persists_selector_cache(self) -> None:
        telegram_sync_runtime.TELEGRAM_SELECTOR_CACHE_STATE_KEY = "_selector_cache"
        telegram_sync_runtime._utc_now = lambda: datetime(2026, 5, 21, tzinfo=timezone.utc)

        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync.state = {}
        sync.client = FakeClient(FakeEntity())
        sync._selector_to_chat_key = {}
        saved = []

        async def ensure_connected():
            return None

        async def sleep_operation_cooldown(operation, context):
            return None

        sync.ensure_connected = ensure_connected
        sync._sleep_operation_cooldown = sleep_operation_cooldown
        sync._clear_operation_cooldown = lambda *args, **kwargs: None
        sync.save_state = lambda: saved.append(True)

        entity = asyncio.run(sync._resolve_entity("@Breakfast", selector_key="@breakfast"))

        self.assertIs(entity, sync.client.entity)
        self.assertEqual(sync.client.selector, "@Breakfast")
        self.assertEqual(sync.state["_selector_cache"]["@breakfast"]["chat_key"], "breakfast_with_harskii")
        self.assertEqual(sync._selector_to_chat_key["@breakfast"], "breakfast_with_harskii")
        self.assertTrue(saved)

    def test_backfill_stop_conditions_are_pure(self) -> None:
        now = datetime(2026, 5, 21, tzinfo=timezone.utc)
        limits = build_backfill_limits(history_months=1, message_limit=30, now=now)

        self.assertEqual(
            backfill_stop_reason(
                total=30,
                message_limit=30,
                message_date=None,
                cutoff_dt=limits.cutoff_dt,
            ),
            "message_limit",
        )
        self.assertEqual(
            backfill_stop_reason(
                total=3,
                message_limit=30,
                message_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                cutoff_dt=limits.cutoff_dt,
            ),
            "history_months",
        )
        self.assertIsNone(
            backfill_stop_reason(
                total=3,
                message_limit=30,
                message_date=now,
                cutoff_dt=limits.cutoff_dt,
            )
        )

    def test_backfill_limits_support_unlimited_history_and_messages(self) -> None:
        now = datetime(2026, 5, 21, tzinfo=timezone.utc)
        limits = build_backfill_limits(history_months=0, message_limit=0, now=now)

        self.assertEqual(limits.history_months, 0)
        self.assertEqual(limits.message_limit, 0)
        self.assertIsNone(limits.cutoff_dt)
        self.assertIsNone(
            backfill_stop_reason(
                total=1_000_000,
                message_limit=limits.message_limit,
                message_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
                cutoff_dt=limits.cutoff_dt,
            )
        )

    def test_runtime_import_limit_int_preserves_unlimited_zero(self) -> None:
        self.assertEqual(telegram_sync_runtime.TelegramSync._import_limit_int(0, 1), 0)
        self.assertEqual(telegram_sync_runtime.TelegramSync._import_limit_int("0", 1000), 0)
        self.assertEqual(telegram_sync_runtime.TelegramSync._import_limit_int("", 1000), 1000)

    def test_rate_limit_helpers_do_not_touch_jsonl_writer(self) -> None:
        class WaitError(Exception):
            seconds = "17"

        state = {}
        current = rate_limit_state(state, "_telegram_rate_limits")
        current["risks"]["chat"] = {"status": "risk_blocked"}

        self.assertEqual(flood_wait_seconds(WaitError("wait")), 17)
        self.assertEqual(flood_wait_seconds(Exception("A wait of 41 seconds is required")), 41)
        self.assertEqual(state["_telegram_rate_limits"]["operation_cooldowns"], {})
        self.assertEqual(state["_telegram_rate_limits"]["risks"]["chat"]["status"], "risk_blocked")

    def test_unresolvable_selector_is_blocked_without_starving_next_sources(self) -> None:
        telegram_sync_runtime._utc_now = lambda: datetime(2026, 5, 21, tzinfo=timezone.utc)
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync.state = {}
        sync.save_state = lambda: None

        sync._mark_selector_setup_failed(
            "2279252035",
            2279252035,
            ValueError("Could not find the input entity for PeerUser(user_id=2279252035)"),
        )

        entry = sync.state["_telegram_selector_setup_failures"]["2279252035"]
        self.assertEqual(entry["status"], "unresolvable")
        self.assertTrue(sync._selector_setup_is_blocked("2279252035"))

    def test_backfill_done_from_old_limit_resumes_when_import_becomes_unlimited(self) -> None:
        telegram_sync_runtime._utc_now = lambda: datetime(2026, 5, 21, tzinfo=timezone.utc)
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync.state = {
            "chat_a": {
                "backfill_done": True,
                "backfill_stop_reason": "history_months",
                "import_history_months": 1,
                "import_message_limit": 1000,
            }
        }
        sync.save_state = lambda: None
        sentinel = object()
        original_limits = getattr(telegram_sync_runtime, "_effective_import_limits_for_selector", sentinel)
        telegram_sync_runtime._effective_import_limits_for_selector = lambda selector: {
            "import_history_months": 0,
            "import_message_limit": 0,
        }
        try:
            self.assertTrue(sync._resume_backfill_if_limits_expanded("chat_a"))
            self.assertFalse(sync.state["chat_a"]["backfill_done"])
            self.assertEqual(sync.state["chat_a"]["backfill_stop_reason"], "limits_expanded")
        finally:
            if original_limits is sentinel:
                delattr(telegram_sync_runtime, "_effective_import_limits_for_selector")
            else:
                telegram_sync_runtime._effective_import_limits_for_selector = original_limits

    def test_refresh_runtime_control_from_disk_updates_selectors_without_losing_chat_progress(self) -> None:
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync.state = {
            "_source_selectors": [],
            "_telegram_sync_control": {"paused": True, "reason": "manual pause"},
            "noirser": {"backfill_items_processed": 37, "max_saved_id": 101},
        }
        sync.load_state = lambda: {
            "_source_selectors": ["noirser"],
            "_telegram_sync_control": {"paused": False, "reason": "resume"},
            "_app_settings": {"telegram_scan_group_assignments": {"noirser": "A"}},
            "_import_dialog_settings": {"noirser": {"import_history_months": 2, "import_message_limit": 2000}},
            "noirser": {"backfill_items_processed": 0},
        }
        reloads = []
        sync.request_source_reload = lambda: reloads.append(True)

        self.assertTrue(sync.refresh_runtime_control_from_disk())
        self.assertEqual(sync.state["_source_selectors"], ["noirser"])
        self.assertFalse(sync.state["_telegram_sync_control"]["paused"])
        self.assertEqual(sync.state["_app_settings"]["telegram_scan_group_assignments"]["noirser"], "A")
        self.assertEqual(sync.state["_import_dialog_settings"]["noirser"]["import_message_limit"], 2000)
        self.assertEqual(sync.state["noirser"]["backfill_items_processed"], 37)
        self.assertEqual(sync.state["noirser"]["max_saved_id"], 101)
        self.assertTrue(reloads)

    def test_scan_group_a_sources_are_prioritized_before_background_sources(self) -> None:
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        original_group_fields = getattr(telegram_sync_runtime, "_lead_scan_group_fields", None)
        original_lead_name = getattr(telegram_sync_runtime, "_selector_to_lead_name", None)
        telegram_sync_runtime._selector_to_lead_name = lambda selector: str(selector).strip()
        telegram_sync_runtime._lead_scan_group_fields = lambda lead, selector=None: {
            "scan_group": "A" if str(selector or lead) == "noirser" else "C"
        }
        try:
            self.assertEqual(sync.sort_selected_chats_for_scan(["background", "noirser"]), ["noirser", "background"])
        finally:
            if original_group_fields is None:
                delattr(telegram_sync_runtime, "_lead_scan_group_fields")
            else:
                telegram_sync_runtime._lead_scan_group_fields = original_group_fields
            if original_lead_name is None:
                delattr(telegram_sync_runtime, "_selector_to_lead_name")
            else:
                telegram_sync_runtime._selector_to_lead_name = original_lead_name

    def test_wait_if_sync_paused_uses_source_poll_interval(self) -> None:
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync._source_poll_interval = 0
        states = iter([True, False])
        sleeps = []
        sync.is_sync_paused = lambda: next(states)
        sync.refresh_runtime_control_from_disk = lambda: None
        sync.get_sync_control_status = lambda: {"paused": True, "reason": "test"}
        original_sleep = asyncio.sleep

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        asyncio.sleep = fake_sleep
        try:
            asyncio.run(sync._wait_if_sync_paused("unit"))
        finally:
            asyncio.sleep = original_sleep
        self.assertEqual(sleeps, [5])

    def test_pause_blocks_telegram_request_until_resume(self) -> None:
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync._source_poll_interval = 0
        states = iter([True, False])
        calls = []
        sleeps = []
        sync.is_sync_paused = lambda: next(states)
        sync.refresh_runtime_control_from_disk = lambda: None
        sync.get_sync_control_status = lambda: {"paused": True, "reason": "test"}
        original_sleep = asyncio.sleep

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        async def guarded_request():
            await sync._wait_if_sync_paused("before-telegram-request")
            calls.append("telegram-request")

        asyncio.sleep = fake_sleep
        try:
            asyncio.run(guarded_request())
        finally:
            asyncio.sleep = original_sleep

        self.assertEqual([5], sleeps)
        self.assertEqual(["telegram-request"], calls)

    def test_set_sync_paused_and_resume_persist_control_state(self) -> None:
        telegram_sync_runtime._utc_now = lambda: datetime(2026, 5, 25, tzinfo=timezone.utc)
        telegram_sync_runtime.TELEGRAM_SYNC_CONTROL_STATE_KEY = "_telegram_sync_control"
        telegram_sync_runtime._append_runtime_log = lambda *args, **kwargs: None
        sync = object.__new__(telegram_sync_runtime.TelegramSync)
        sync.state = {}
        saved = []
        sync.save_state = lambda: saved.append(json.loads(json.dumps(sync.state)))

        paused = sync.set_sync_paused(True, reason="manual test")
        resumed = sync.set_sync_paused(False, reason="resume test")

        self.assertTrue(paused["paused"])
        self.assertEqual("manual test", paused["reason"])
        self.assertFalse(resumed["paused"])
        self.assertEqual("resume test", resumed["reason"])
        self.assertEqual(2, len(saved))
        self.assertFalse(saved[-1]["_telegram_sync_control"]["paused"])

    def test_existing_jsonl_message_bounds_skips_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"message": {"id": 10}}),
                        "{bad",
                        json.dumps({"message": {"id": 4}}),
                        json.dumps({"message": {"id": 21}}),
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(existing_jsonl_message_bounds(path), {"min_id": 4, "max_id": 21, "total": 3})


if __name__ == "__main__":
    unittest.main()
