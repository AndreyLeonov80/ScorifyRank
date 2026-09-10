from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.schemas.compat_models import LeadDTO
from app.services import leads


class ImportGridDashboardCountsMatchTest(unittest.TestCase):
    def test_source_stats_and_runtime_status_summaries_match(self) -> None:
        fixture = [
            LeadDTO(
                name="active_group",
                file="active_group.jsonl",
                count=100,
                in_source=True,
                has_jsonl=True,
                sync_status="active",
                source_selector="active_group",
                chat_type="group",
                telegram_active=True,
                read_messages_count=60,
                total_messages_estimate=100,
                remaining_messages_estimate=40,
            ),
            LeadDTO(
                name="waiting_channel",
                file="waiting_channel.jsonl",
                count=25,
                in_source=True,
                has_jsonl=True,
                sync_status="active",
                source_selector="waiting_channel",
                chat_type="channel",
                read_messages_count=25,
                total_messages_estimate=25,
                remaining_messages_estimate=0,
            ),
            LeadDTO(
                name="not_selected_private",
                file="not_selected_private.jsonl",
                count=10,
                in_source=False,
                has_jsonl=True,
                sync_status="archived",
                source_selector="not_selected_private",
                chat_type="private",
                read_messages_count=10,
                total_messages_estimate=10,
                remaining_messages_estimate=0,
            ),
        ]

        async def fake_loader(**_kwargs):
            return fixture

        async def no_cache(_key, factory, **_kwargs):
            return await factory()

        with patch.object(leads, "_load_leads_for_source_view", side_effect=fake_loader):
            with patch.object(leads, "_cached_async_snapshot", side_effect=no_cache):
                source_stats = asyncio.run(leads.api_payme_source_stats(page=1, page_size=50))
                runtime_status = asyncio.run(leads.api_payme_sources_runtime_status(page=1, page_size=50))

        self.assertEqual(source_stats.total, runtime_status.total)
        self.assertEqual(source_stats.summary.total_sources, runtime_status.summary.total_sources)
        self.assertEqual(source_stats.summary.selected_sources, runtime_status.summary.selected_sources)
        self.assertEqual(source_stats.summary.imported_sources, runtime_status.summary.imported_sources)
        self.assertEqual(source_stats.summary.active_sources, runtime_status.summary.active_sources)
        self.assertEqual(source_stats.summary.messages_total, runtime_status.summary.messages_total)
        self.assertEqual(source_stats.summary.messages_read, runtime_status.summary.messages_read)
        self.assertEqual(source_stats.summary.messages_remaining, runtime_status.summary.messages_remaining)


if __name__ == "__main__":
    unittest.main()
