from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import monitoring


class DashboardSummaryLiteBudgetTest(unittest.TestCase):
    def test_lite_payload_is_small_and_excludes_heavy_sections(self) -> None:
        with patch.object(monitoring, "_build_duckdb_status", return_value={
            "source_files_indexed": 12,
            "source_files_total": 12,
            "message_rows": 3456,
            "running": False,
            "cache_ready": True,
            "progress_percent": 100.0,
        }):
            with patch.object(monitoring, "_build_analysis_status", return_value=SimpleNamespace(total_rows=77)):
                with patch.object(monitoring, "_xfiles_deals_status_sync", return_value=SimpleNamespace(total=3)):
                    with patch.object(monitoring, "_source_selectors_as_strings", return_value=["a", "b", "b"]):
                        with patch.object(monitoring, "_sum_glob_file_sizes", return_value=1234):
                            with patch.object(monitoring, "_safe_file_size", return_value=5678):
                                with patch.object(monitoring, "_compute_import_sync_status", return_value=SimpleNamespace(model_dump=lambda: {"enabled": True, "pending_dialogs": 2})):
                                    with patch.object(monitoring, "_cached_sync_snapshot_fast", return_value=SimpleNamespace(total=3)):
                                        with patch.object(monitoring.telegram_sync, "get_sync_control_status", return_value={"paused": False}):
                                            payload = monitoring._dashboard_summary_lite_payload_sync()

        raw = json.dumps(payload, ensure_ascii=False)
        self.assertLess(len(raw.encode("utf-8")), 50_000)
        self.assertEqual("lite", payload["mode"])
        self.assertEqual(12, payload["counts"]["leads"])
        self.assertEqual(3456, payload["counts"]["messages"])
        self.assertEqual(2, payload["counts"]["selected_sources"])
        self.assertIn("duckdb_sync", payload)
        self.assertIn("duckdb_path", payload["storage"])
        self.assertIn("db_path", payload["duckdb_sync"])
        self.assertEqual(12, payload["duckdb_sync"]["files_on_disk"])
        self.assertEqual(2, payload["duckdb_sync"]["files_selected"])
        self.assertEqual(12, payload["duckdb_sync"]["files_indexed"])
        self.assertEqual(0, payload["duckdb_sync"]["files_with_rows"])
        self.assertNotIn("previews", payload)
        self.assertNotIn("system", payload)
        self.assertNotIn("runtime", payload)


if __name__ == "__main__":
    unittest.main()
