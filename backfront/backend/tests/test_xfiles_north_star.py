import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import back


class XFilesNorthStarTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_deals = back.telegram_sync.state.get(back.XFILES_DEALS_STATE_KEY)
        self._original_metric_history = back.telegram_sync.state.get(back.XFILES_METRIC_HISTORY_STATE_KEY)
        self._original_llm_audit = back.telegram_sync.state.get(back.XFILES_LLM_AUDIT_STATE_KEY)
        back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = {"items": []}
        back.telegram_sync.state[back.XFILES_METRIC_HISTORY_STATE_KEY] = {"items": []}
        back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY] = {"items": []}
        back._xfiles_clear_deal_api_caches()

    def tearDown(self) -> None:
        if self._original_deals is None:
            back.telegram_sync.state.pop(back.XFILES_DEALS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = self._original_deals
        if self._original_metric_history is None:
            back.telegram_sync.state.pop(back.XFILES_METRIC_HISTORY_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_METRIC_HISTORY_STATE_KEY] = self._original_metric_history
        if self._original_llm_audit is None:
            back.telegram_sync.state.pop(back.XFILES_LLM_AUDIT_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY] = self._original_llm_audit
        back._xfiles_clear_deal_api_caches()

    def _deal(self, deal_id: str, stage: back.DealStage, expected_profit: float) -> back.XFilesDealDTO:
        return back.XFilesDealDTO(
            id=deal_id,
            title=f"Revenue deal {deal_id}",
            stage=stage,
            score=80,
            expected_value=expected_profit * 2.0,
            probability=0.5,
            margin=0.5,
            expected_profit=expected_profit,
            contact_key=f"contact:{deal_id}",
            contact_name=f"Contact {deal_id}",
            source="test",
            source_chat="north-star-source",
            need="Нужно быстрее квалифицировать и довести до договора.",
            product_match="X-Files revenue operating system",
            next_action="Написать follow-up",
            next_action_at="2026-05-06T11:00:00+00:00",
            created_at="2026-05-06T08:00:00+00:00",
            updated_at="2026-05-06T09:00:00+00:00",
        )

    def test_north_star_returns_function_impacts_and_daily_history(self) -> None:
        fixed_now = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
            patch.object(back, "_utc_now", return_value=fixed_now),
            patch.object(
                back,
                "_lead_scan_group_fields",
                lambda _lead, _selector: {"scan_group": "C", "scan_group_label": "C — фоновые"},
            ),
        ):
            back._xfiles_upsert_deal(self._deal("one", "qualified", 120000.0))
            back._xfiles_upsert_deal(self._deal("two", "proposal", 80000.0))

            first = back.api_payme_deals_north_star()
            back._xfiles_clear_deal_api_caches()
            second = back.api_payme_deals_north_star()

        self.assertGreater(first.pipeline_profit_per_attention_hour, 0.0)
        self.assertEqual(first.qualified_leads_per_day, 2.0)
        self.assertEqual({item.value_type for item in first.function_impacts}, {"money", "time", "risk", "speed"})
        self.assertTrue(any(item.key == "deal_profit_engine" and item.earned_money > 0 for item in first.function_impacts))
        self.assertTrue(any(item.key == "contact_qualification" and item.saved_time_minutes > 0 for item in first.function_impacts))
        self.assertEqual([item.date for item in first.history], ["2026-05-06"])
        self.assertEqual([item.date for item in second.history], ["2026-05-06"])
        self.assertIn("revenue operating system", first.message)


if __name__ == "__main__":
    unittest.main()
