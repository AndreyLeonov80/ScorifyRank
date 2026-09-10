import unittest
from unittest.mock import patch

import back


class XFilesDealPageCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self._clear_deal_cache()

    def tearDown(self) -> None:
        self._clear_deal_cache()

    def _clear_deal_cache(self) -> None:
        for prefix in (
            "xfiles_deals_status",
            "xfiles_deals:",
            "xfiles_deals_kanban:",
            "xfiles_deals_audit:",
            "xfiles_deal_reminders:",
            "xfiles_deal_conversion",
            "xfiles_profit_optimization",
            "xfiles_north_star",
            "xfiles_contract_templates",
            "xfiles_contract_metrics",
            "xfiles_deal_assistant:",
            "xfiles_deal_contract_kit:",
            "xfiles_daily_contacts:",
            "xfiles_event_sales_plan:",
            "dashboard_summary:",
        ):
            back._api_snapshot_cache_clear_prefix(prefix)

    def _deal(self) -> back.XFilesDealDTO:
        return back.XFilesDealDTO(
            id="deal-cache-1",
            title="Кешируемая сделка",
            stage="lead",
            expected_value=100000.0,
            probability=0.5,
            margin=0.4,
            expected_profit=20000.0,
            contact_key="contact:cache",
            source="test",
            created_at="2026-05-06T10:00:00+00:00",
            updated_at="2026-05-06T10:00:00+00:00",
        )

    def test_deal_page_endpoints_use_snapshot_cache(self) -> None:
        calls = {
            "list": 0,
            "kanban": 0,
            "status": 0,
            "audit": 0,
        }
        deal = self._deal()

        def load_deals(**_kwargs):
            calls["list"] += 1
            return [deal]

        def load_kanban(**_kwargs):
            calls["kanban"] += 1
            return back.XFilesDealsKanbanDTO(
                items=[
                    back.XFilesDealsKanbanColumnDTO(
                        stage="lead",
                        label="Лиды",
                        items=[deal],
                        total=1,
                        expected_profit=deal.expected_profit,
                    )
                ],
                total=1,
                limit_per_stage=20,
            )

        def load_status():
            calls["status"] += 1
            return back.XFilesDealsStatusDTO(total=1, active=1, pipeline_profit=deal.expected_profit)

        def load_audit(**_kwargs):
            calls["audit"] += 1
            return [
                back.XFilesDealAuditDTO(
                    id="audit-cache-1",
                    ts="2026-05-06T10:00:00+00:00",
                    action="create",
                    deal_id=deal.id,
                    deal_title=deal.title,
                    after_stage="lead",
                )
            ]

        with (
            patch.object(back, "_xfiles_load_deals", load_deals),
            patch.object(back, "_xfiles_deals_kanban_sync", load_kanban),
            patch.object(back, "_xfiles_deals_status_sync", load_status),
            patch.object(back, "_xfiles_load_deal_audit", load_audit),
        ):
            first_list = back.api_payme_deals(page=1, page_size=10, query="", stage="", limit=10)
            second_list = back.api_payme_deals(page=1, page_size=10, query="", stage="", limit=10)
            first_kanban = back.api_payme_deals_kanban(query="", stage="", limit_per_stage=20)
            second_kanban = back.api_payme_deals_kanban(query="", stage="", limit_per_stage=20)
            first_status = back.api_payme_deals_status()
            second_status = back.api_payme_deals_status()
            first_audit = back.api_payme_deals_audit(page=1, page_size=10, limit=20)
            second_audit = back.api_payme_deals_audit(page=1, page_size=10, limit=20)

        self.assertEqual(first_list.total, 1)
        self.assertEqual(second_list.total, 1)
        self.assertEqual(first_kanban.total, 1)
        self.assertEqual(second_kanban.total, 1)
        self.assertEqual(first_status.pipeline_profit, 20000.0)
        self.assertEqual(second_status.pipeline_profit, 20000.0)
        self.assertEqual(first_audit.total, 1)
        self.assertEqual(second_audit.total, 1)
        self.assertEqual(calls, {"list": 1, "kanban": 1, "status": 1, "audit": 1})

    def test_deal_cache_clear_helper_invalidates_deal_snapshots(self) -> None:
        back._api_snapshot_cache_set("xfiles_deals:demo", {"items": [1]}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_deals_kanban:demo", {"items": [1]}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_deals_status", {"total": 1}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_deal_reminders:10:False", {"items": [1]}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_deal_conversion", {"deal_total": 1}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_profit_optimization", {"ranked_tasks": [1]}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_north_star", {"function_impacts": [1]}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_contract_templates", {"total": 1}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_contract_metrics", {"deals_total": 1}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_deal_assistant:deal-1", {"messages": [1]}, ttl_sec=60)
        back._api_snapshot_cache_set("xfiles_deal_contract_kit:deal-1", {"fields": [1]}, ttl_sec=60)
        back._api_snapshot_cache_set("dashboard_summary:10", {"counts": {"deals": 1}}, ttl_sec=60)

        back._xfiles_clear_deal_api_caches(schedule_warmup=False)

        self.assertIsNone(back._api_snapshot_cache_get("xfiles_deals:demo"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_deals_kanban:demo"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_deals_status"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_deal_reminders:10:False"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_deal_conversion"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_profit_optimization"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_north_star"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_contract_templates"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_contract_metrics"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_deal_assistant:deal-1"))
        self.assertIsNone(back._api_snapshot_cache_get("xfiles_deal_contract_kit:deal-1"))
        self.assertIsNone(back._api_snapshot_cache_get("dashboard_summary:10"))

    def test_fast_snapshot_returns_stale_value_and_schedules_refresh(self) -> None:
        key = "xfiles_fast_stale_demo"
        with back._api_snapshot_cache_lock:
            back._api_snapshot_cache[key] = {
                "value": {"cached": True},
                "created_at": back.time.monotonic() - 2.0,
                "expires_at": back.time.monotonic() - 1.0,
            }

        calls = {"factory": 0, "refresh": 0}

        def factory():
            calls["factory"] += 1
            return {"cached": False}

        def refresh(_key, _factory, ttl_sec=1.0):
            calls["refresh"] += 1
            return True

        with patch.object(back, "_schedule_snapshot_refresh", refresh):
            value = back._cached_sync_snapshot_fast(key, factory, ttl_sec=1.0, stale_ttl_sec=60.0)

        self.assertEqual(value, {"cached": True})
        self.assertEqual(calls, {"factory": 0, "refresh": 1})

    def test_xfiles_deal_cache_status_is_exposed_as_background_task(self) -> None:
        back._api_snapshot_cache_set(
            "xfiles_deals_status",
            back.XFilesDealsStatusDTO(total=2, active=1, pipeline_profit=50000.0),
            ttl_sec=60,
        )
        with back._xfiles_deal_cache_warm_status_lock:
            back._xfiles_deal_cache_warm_status.update(
                {
                    "running": False,
                    "progress_current": 13,
                    "progress_total": 13,
                    "progress_percent": 100.0,
                    "updated_at": "2026-05-06T10:00:00+00:00",
                    "last_error": None,
                }
            )

        rows = back._background_task_statuses()
        task = next(item for item in rows if item.kind == "xfiles_deal_cache")

        self.assertEqual(task.status, "idle")
        self.assertTrue(task.cache_ready)
        self.assertEqual(task.total_rows, 2)
        self.assertEqual(task.progress_percent, 100.0)


if __name__ == "__main__":
    unittest.main()
