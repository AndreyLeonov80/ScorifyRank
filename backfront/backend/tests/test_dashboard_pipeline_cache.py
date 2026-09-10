import asyncio
import time
import unittest
from unittest.mock import patch

import back


class DashboardPipelineCacheTest(unittest.TestCase):
    def tearDown(self) -> None:
        back._api_snapshot_cache_clear_prefix("dashboard_summary:")
        back._api_snapshot_cache_clear_prefix("xfiles_deals_status")

    def test_dashboard_pipeline_metrics_are_served_from_cache_under_one_second(self) -> None:
        calls = 0

        async def slow_dashboard_payload(limit: int = 10) -> dict:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)
            return {
                "counts": {
                    "deals": 3,
                    "active_deals": 2,
                    "pipeline_value": 900000.0,
                    "pipeline_profit": 360000.0,
                    "expected_deal_profit": 180000.0,
                    "pipeline_profit_per_attention_hour": 12000.0,
                },
                "deals": {
                    "total": 3,
                    "pipeline_value": 900000.0,
                    "pipeline_profit": 360000.0,
                },
            }

        async def run_check() -> tuple[dict, dict, float]:
            back._api_snapshot_cache_clear_prefix("dashboard_summary:")
            with patch("back._dashboard_summary_payload", slow_dashboard_payload):
                first = await back.api_payme_dashboard_summary(limit=10)
                start = time.perf_counter()
                second = await back.api_payme_dashboard_summary(limit=10)
                elapsed = time.perf_counter() - start
            return first, second, elapsed

        first, second, elapsed = asyncio.run(run_check())

        self.assertEqual(calls, 1)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(second["counts"]["pipeline_value"], 900000.0)
        self.assertEqual(second["counts"]["pipeline_profit"], 360000.0)
        self.assertEqual(second["counts"]["expected_deal_profit"], 180000.0)
        self.assertEqual(second["deals"]["pipeline_profit"], 360000.0)
        self.assertEqual(first, second)

    def test_dashboard_summary_reuses_cached_xfiles_deal_status(self) -> None:
        cached_deals = back.XFilesDealsStatusDTO(
            total=7,
            active=5,
            won=1,
            lost=1,
            pipeline_value=1200000.0,
            pipeline_profit=420000.0,
            expected_profit=420000.0,
        )
        back._api_snapshot_cache_set("xfiles_deals_status", cached_deals, ttl_sec=60)

        async def runtime_status():
            return back.RuntimeStatusDTO(
                auth_status="unknown",
                auth_message="test",
                session_file_exists=False,
                connected=False,
            )

        def duckdb_status():
            return back.DuckDbStatusDTO(
                available=True,
                enabled=True,
                running=False,
                cache_ready=True,
                db_path=":memory:",
                source_files_indexed=3,
                source_files_total=3,
                message_rows=100,
            )

        def analysis_status(kind):
            return back.AnalysisStatusDTO(
                kind=kind,
                enabled=True,
                interval_sec=300,
                running=False,
                cache_ready=True,
                total_rows=10,
            )

        def media_status():
            return back.MediaStatusDTO(
                enabled=True,
                running=False,
                cache_ready=True,
                total_rows=2,
                query="",
                total_matches=2,
            )

        def import_status():
            return back.ImportSyncStatusDTO(
                enabled=False,
                running=False,
                total_dialogs=0,
                completed_dialogs=0,
                pending_dialogs=0,
                progress_percent=0.0,
                message="disabled",
            )

        async def run_check() -> dict:
            with (
                patch(
                    "back._xfiles_deals_status_sync",
                    side_effect=AssertionError("dashboard must use cached deals status"),
                ),
                patch("back._runtime_status", runtime_status),
                patch("back._build_duckdb_status", duckdb_status),
                patch("back._build_analysis_status", analysis_status),
                patch("back._build_media_status", media_status),
                patch("back._compute_import_sync_status", import_status),
                patch(
                    "back._system_metrics_payload",
                    lambda history_points=30: {"history": [], "tasks": []},
                ),
                patch(
                    "back._server_runtime_snapshot",
                    lambda: {
                        "instance_id": "test",
                        "started_at": "2026-05-06T10:00:00+00:00",
                        "uptime_sec": 1,
                        "pid": 1,
                        "hostname": "test",
                        "mode": "local",
                    },
                ),
                patch.object(
                    back.telegram_sync,
                    "get_global_flood_wait_status",
                    return_value={"active": False},
                ),
                patch.object(
                    back.telegram_sync,
                    "get_rate_limit_status",
                    return_value={"operation_cooldowns": {}},
                ),
                patch.object(
                    back.telegram_sync,
                    "get_sync_control_status",
                    return_value={"paused": False},
                ),
            ):
                return await back._dashboard_summary_payload(limit=10)

        payload = asyncio.run(run_check())

        self.assertEqual(payload["counts"]["deals"], 7)
        self.assertEqual(payload["counts"]["pipeline_profit"], 420000.0)
        self.assertEqual(payload["deals"]["total"], 7)
        self.assertEqual(payload["xfiles"]["deals"]["pipeline_value"], 1200000.0)


if __name__ == "__main__":
    unittest.main()
