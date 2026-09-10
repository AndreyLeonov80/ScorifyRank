from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.schemas.compat_models import LeadDTO
from app.services import leads


class SourceStatsContractTest(unittest.TestCase):
    def test_source_stats_returns_paged_items_and_unified_summary(self) -> None:
        loader_calls = []

        async def fake_loader(**kwargs):
            loader_calls.append(kwargs)
            return [
                LeadDTO(
                    name="active_chat",
                    file="active_chat.jsonl",
                    count=80,
                    in_source=True,
                    has_jsonl=True,
                    sync_status="active",
                    source_selector="active_chat",
                    telegram_active=True,
                    telegram_active_stage="setup",
                    read_messages_count=80,
                    total_messages_estimate=100,
                    remaining_messages_estimate=20,
                    read_progress_percent=80.0,
                ),
                LeadDTO(
                    name="pending_chat",
                    file="pending_chat.jsonl",
                    count=0,
                    in_source=True,
                    has_jsonl=False,
                    sync_status="pending",
                    source_selector="pending_chat",
                    read_messages_count=0,
                    total_messages_estimate=1000,
                    remaining_messages_estimate=1000,
                    read_progress_percent=0.0,
                ),
                LeadDTO(
                    name="archived_chat",
                    file="archived_chat.jsonl",
                    count=12,
                    in_source=False,
                    has_jsonl=True,
                    sync_status="archived",
                    source_selector="archived_chat",
                    read_messages_count=12,
                    total_messages_estimate=12,
                    remaining_messages_estimate=0,
                    read_progress_percent=100.0,
                ),
            ]

        async def no_cache(_key, factory, **_kwargs):
            return await factory()

        with patch.object(leads, "_load_leads_for_source_view", side_effect=fake_loader):
            with patch.object(leads, "_cached_async_snapshot", side_effect=no_cache):
                payload = asyncio.run(leads.api_payme_source_stats(page=1, page_size=2, scan_filter="scanning"))

        self.assertEqual(3, payload.total)
        self.assertEqual(2, len(payload.items))
        self.assertEqual(3, payload.summary.total_sources)
        self.assertEqual(2, payload.summary.selected_sources)
        self.assertEqual(2, payload.summary.imported_sources)
        self.assertEqual(1, payload.summary.active_sources)
        self.assertEqual(1, payload.summary.pending_sources)
        self.assertEqual(1, payload.summary.archived_sources)
        self.assertEqual(1112, payload.summary.messages_total)
        self.assertEqual(92, payload.summary.messages_read)
        self.assertEqual(1020, payload.summary.messages_remaining)
        self.assertAlmostEqual(8.27, payload.summary.progress_percent)
        self.assertEqual("scanning", loader_calls[0]["scan_filter"])


if __name__ == "__main__":
    unittest.main()
