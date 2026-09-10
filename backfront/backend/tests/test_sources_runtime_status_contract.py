from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.schemas.compat_models import LeadDTO
from app.services import leads


class SourcesRuntimeStatusContractTest(unittest.TestCase):
    def test_selected_bot_source_is_not_hidden_from_sync_contract(self) -> None:
        selected_bot = LeadDTO(
            name="faino_psy_bot",
            file="faino_psy_bot.jsonl",
            count=0,
            in_source=True,
            has_jsonl=False,
            sync_status="pending",
            source_selector="faino_psy_bot",
            chat_type="bot",
        )
        unselected_bot = LeadDTO(
            name="other_bot",
            file="other_bot.jsonl",
            count=0,
            in_source=False,
            has_jsonl=False,
            sync_status="archived",
            source_selector="other_bot",
            chat_type="bot",
        )

        self.assertTrue(
            leads._lead_matches_filters(
                selected_bot,
                show_channels=True,
                show_groups=True,
                show_private=True,
                show_bots=False,
                show_archived=False,
            )
        )
        self.assertFalse(
            leads._lead_matches_filters(
                unselected_bot,
                show_channels=True,
                show_groups=True,
                show_private=True,
                show_bots=False,
                show_archived=False,
            )
        )

    def test_runtime_status_returns_unified_source_contract(self) -> None:
        async def fake_loader(**_kwargs):
            return [
                LeadDTO(
                    name="waiting_chat",
                    file="waiting_chat.jsonl",
                    count=25,
                    in_source=True,
                    has_jsonl=True,
                    sync_status="active",
                    source_selector="waiting_chat",
                    chat_type="channel",
                    read_messages_count=25,
                    total_messages_estimate=25,
                    remaining_messages_estimate=0,
                    read_progress_percent=100.0,
                ),
                LeadDTO(
                    name="breakfast_with_harskii",
                    file="breakfast_with_harskii.jsonl",
                    count=18617,
                    last_date_utc="2026-05-25T04:18:39+00:00",
                    in_source=True,
                    has_jsonl=True,
                    sync_status="active",
                    source_selector="breakfast_with_harskii",
                    chat_type="group",
                    scan_group="A",
                    scan_group_label="A — критичные продажи/лиды",
                    import_history_months=2,
                    import_message_limit=2000,
                    telegram_active=True,
                    telegram_active_stage="history",
                    backfill_running=True,
                    read_messages_count=1500,
                    total_messages_estimate=2000,
                    remaining_messages_estimate=500,
                    read_progress_percent=75.0,
                ),
            ]

        async def no_cache(_key, factory, **_kwargs):
            return await factory()

        with patch.object(leads, "_load_leads_for_source_view", side_effect=fake_loader):
            with patch.object(leads, "_cached_async_snapshot", side_effect=no_cache):
                payload = asyncio.run(leads.api_payme_sources_runtime_status(page=1, page_size=10))

        self.assertEqual(2, payload.total)
        self.assertEqual(2, payload.summary.selected_sources)
        self.assertEqual(2, payload.summary.imported_sources)
        self.assertEqual(1, payload.summary.active_sources)

        first = payload.items[0]
        self.assertEqual("breakfast_with_harskii", first.selector)
        self.assertEqual("breakfast_with_harskii", first.title)
        self.assertEqual("group", first.chat_type)
        self.assertTrue(first.is_selected)
        self.assertTrue(first.has_jsonl)
        self.assertEqual(18617, first.duckdb_rows)
        self.assertTrue(first.read_now)
        self.assertEqual("history", first.read_stage)
        self.assertTrue(first.backfill_running)
        self.assertFalse(first.setup_running)
        self.assertFalse(first.live_connected)
        self.assertEqual(1500, first.read_done)
        self.assertEqual(2000, first.read_total)
        self.assertEqual(500, first.remaining)
        self.assertEqual(75.0, first.progress_percent)
        self.assertEqual("A", first.scan_group)
        self.assertEqual(2, first.limit_months)
        self.assertEqual(2000, first.limit_messages)
        self.assertEqual("2026-05-25T04:18:39+00:00", first.last_message_at)
        self.assertEqual("reading", first.status)
        self.assertIn("читает сейчас", first.status_reason)

    def test_runtime_status_separates_live_setup_pause_and_cooldown(self) -> None:
        fixture = [
            LeadDTO(
                name="live_chat",
                file="live_chat.jsonl",
                count=5,
                in_source=True,
                has_jsonl=True,
                sync_status="active",
                source_selector="live_chat",
                chat_type="group",
                telegram_active=True,
                telegram_active_stage="live",
                live_connected=True,
                last_live_update_at="2026-05-25T05:00:00+00:00",
            ),
            LeadDTO(
                name="paused_chat",
                file="paused_chat.jsonl",
                count=0,
                in_source=True,
                has_jsonl=False,
                sync_status="pending",
                source_selector="paused_chat",
                chat_type="channel",
                telegram_status="paused",
                paused=True,
            ),
            LeadDTO(
                name="cooldown_chat",
                file="cooldown_chat.jsonl",
                count=3,
                in_source=True,
                has_jsonl=True,
                sync_status="active",
                source_selector="cooldown_chat",
                chat_type="channel",
                telegram_status="cooldown",
                cooldown=True,
            ),
        ]

        async def fake_loader(**_kwargs):
            return fixture

        async def no_cache(_key, factory, **_kwargs):
            return await factory()

        with patch.object(leads, "_load_leads_for_source_view", side_effect=fake_loader):
            with patch.object(leads, "_cached_async_snapshot", side_effect=no_cache):
                payload = asyncio.run(leads.api_payme_sources_runtime_status(page=1, page_size=10))

        by_selector = {item.selector: item for item in payload.items}
        self.assertTrue(by_selector["live_chat"].live_connected)
        self.assertEqual("2026-05-25T05:00:00+00:00", by_selector["live_chat"].last_live_update_at)
        self.assertTrue(by_selector["paused_chat"].paused)
        self.assertIn("пауза", by_selector["paused_chat"].status_reason)
        self.assertTrue(by_selector["cooldown_chat"].cooldown)
        self.assertIn("cooldown", by_selector["cooldown_chat"].status_reason.lower())


if __name__ == "__main__":
    unittest.main()
