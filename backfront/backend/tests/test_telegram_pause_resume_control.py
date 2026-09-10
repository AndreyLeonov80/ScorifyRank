from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.services import channels


class TelegramPauseResumeControlTest(unittest.TestCase):
    def test_resume_returns_worker_to_queue_and_unpauses_status(self) -> None:
        class FakeTelegramSync:
            def __init__(self):
                self.reloaded = False

            def set_sync_paused(self, paused, reason=None):
                return {"paused": bool(paused), "reason": reason}

            def request_source_reload(self):
                self.reloaded = True

        fake_sync = FakeTelegramSync()
        ensured = []
        cleared = []

        with patch.object(channels, "telegram_sync", fake_sync):
            with patch.object(channels, "_ensure_telegram_sync_worker_job", side_effect=lambda reason: ensured.append(reason)):
                with patch.object(channels, "_api_snapshot_cache_clear_prefix", side_effect=lambda prefix: cleared.append(prefix)):
                    payload = asyncio.run(channels.api_payme_telegram_sync_resume(reason="unit-test"))

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["status"]["paused"])
        self.assertEqual(["dashboard_summary:"], cleared)
        self.assertEqual(["resume"], ensured)
        self.assertTrue(fake_sync.reloaded)


if __name__ == "__main__":
    unittest.main()
