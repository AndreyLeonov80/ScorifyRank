import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import back


class XFilesProfitOptimizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_deals = back.telegram_sync.state.get(back.XFILES_DEALS_STATE_KEY)
        self._original_llm_audit = back.telegram_sync.state.get(back.XFILES_LLM_AUDIT_STATE_KEY)
        back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = {"items": []}
        back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY] = {"items": []}
        back._xfiles_clear_deal_api_caches()

    def tearDown(self) -> None:
        if self._original_deals is None:
            back.telegram_sync.state.pop(back.XFILES_DEALS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = self._original_deals
        if self._original_llm_audit is None:
            back.telegram_sync.state.pop(back.XFILES_LLM_AUDIT_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY] = self._original_llm_audit
        back._xfiles_clear_deal_api_caches()

    def _deal(
        self,
        deal_id: str,
        stage: back.DealStage,
        source_chat: str,
        expected_profit: float,
        score: int = 70,
    ) -> back.XFilesDealDTO:
        return back.XFilesDealDTO(
            id=deal_id,
            title=f"Сделка {deal_id}",
            stage=stage,
            score=score,
            expected_value=expected_profit * 2 if expected_profit else 0.0,
            probability=0.5,
            margin=1.0,
            expected_profit=expected_profit,
            contact_key=f"contact:{deal_id}",
            contact_name=f"Contact {deal_id}",
            source="test",
            source_chat=source_chat,
            need="Нужно быстро понять потребность и довести до следующего шага.",
            product_match="X-Files revenue operating system",
            next_action="Написать сегодня",
            next_action_at="2026-05-06T12:00:00+00:00",
            created_at="2026-05-06T08:00:00+00:00",
            updated_at="2026-05-06T08:00:00+00:00",
        )

    def _seed_llm_audit(self) -> None:
        back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY] = {
            "items": [
                {
                    "request_id": "good-1",
                    "kind": "contact_qualification",
                    "provider": "openrouter",
                    "model": "openai/gpt-oss-120b:free",
                    "prompt_hash": "prompt-good",
                    "input_ids": {"template_id": "needs_priority", "contact_key": "contact:1"},
                    "status": "ready",
                    "duration_sec": 1.0,
                    "cost_estimate_usd": 0.0,
                    "input_tokens_estimate": 1000,
                    "output_tokens_estimate": 400,
                    "total_tokens_estimate": 1400,
                    "created_at": "2026-05-06T08:00:00+00:00",
                },
                {
                    "request_id": "good-2",
                    "kind": "contact_qualification",
                    "provider": "openrouter",
                    "model": "openai/gpt-oss-120b:free",
                    "prompt_hash": "prompt-good",
                    "input_ids": {"template_id": "needs_priority", "contact_key": "contact:2"},
                    "status": "ready",
                    "duration_sec": 2.0,
                    "cost_estimate_usd": 0.0,
                    "input_tokens_estimate": 1200,
                    "output_tokens_estimate": 450,
                    "total_tokens_estimate": 1650,
                    "created_at": "2026-05-06T08:01:00+00:00",
                },
                {
                    "request_id": "bad-1",
                    "kind": "contact_qualification",
                    "provider": "openrouter",
                    "model": "paid/model",
                    "prompt_hash": "prompt-bad",
                    "input_ids": {"template_id": "first_message", "contact_key": "contact:3"},
                    "status": "error",
                    "duration_sec": 12.0,
                    "cost_estimate_usd": 0.02,
                    "input_tokens_estimate": 1400,
                    "output_tokens_estimate": 0,
                    "total_tokens_estimate": 1400,
                    "created_at": "2026-05-06T08:02:00+00:00",
                },
            ]
        }

    def test_profit_optimization_ranks_tasks_sources_costs_and_templates(self) -> None:
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
            back._xfiles_upsert_deal(self._deal("strong-1", "qualified", "strong-source", 120000.0, score=82))
            back._xfiles_upsert_deal(self._deal("strong-2", "proposal", "strong-source", 60000.0, score=75))
            for index in range(5):
                back._xfiles_upsert_deal(self._deal(f"weak-{index}", "lead", "weak-source", 0.0, score=20))
            self._seed_llm_audit()

            optimization = back.api_payme_deals_profit_optimization()

        self.assertGreaterEqual(optimization.profit_per_user_hour, 0.0)
        self.assertEqual(optimization.ranked_tasks[0]["deal_id"], "strong-1")
        self.assertIn("cost_per_qualified_lead_usd", optimization.cost_metrics)
        self.assertTrue(any(row["source"] == "strong-source" for row in optimization.source_roi))
        self.assertTrue(
            any(row["source"] == "strong-source" and row["recommendation"] == "promote" for row in optimization.source_group_recommendations)
        )
        self.assertTrue(
            any(row["source"] == "weak-source" and row["recommendation"] == "deprioritize" for row in optimization.source_group_recommendations)
        )
        good_benchmark = next(
            item for item in optimization.template_model_benchmarks if item.template_id == "needs_priority"
        )
        self.assertEqual(good_benchmark.recommendation, "keep")
        self.assertEqual(good_benchmark.ready, 2)
        bad_benchmark = next(
            item for item in optimization.template_model_benchmarks if item.template_id == "first_message"
        )
        self.assertEqual(bad_benchmark.recommendation, "replace_or_tune")
        self.assertTrue(optimization.recommendations)
        self.assertIn("Profit optimization", optimization.message)


if __name__ == "__main__":
    unittest.main()
