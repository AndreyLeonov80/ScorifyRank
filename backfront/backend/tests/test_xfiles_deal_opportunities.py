import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import back


class XFilesDealOpportunitiesTest(unittest.TestCase):
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
        expected_value: float,
        probability: float,
        margin: float,
        score: int,
        contact_name: str,
    ) -> back.XFilesDealDTO:
        expected_profit = back._xfiles_expected_profit(expected_value, probability, margin)
        return back.XFilesDealDTO(
            id=deal_id,
            title=f"Opportunity {deal_id}",
            stage=stage,
            score=score,
            expected_value=expected_value,
            probability=probability,
            margin=margin,
            expected_profit=expected_profit,
            contact_key=f"contact:{deal_id}",
            contact_name=contact_name,
            company="Client Co",
            source="test",
            source_chat="opportunity-source",
            source_message_id=f"msg-{deal_id}",
            need="Нужно быстро квалифицировать клиента и довести до договора.",
            product_match="X-Files revenue operating system",
            next_action="Написать персональный follow-up и предложить короткий созвон",
            next_action_at="2026-05-06T11:00:00+00:00",
            created_at="2026-05-06T08:00:00+00:00",
            updated_at="2026-05-06T09:00:00+00:00",
        )

    def test_opportunities_rank_deals_and_explain_next_money_action(self) -> None:
        fixed_now = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
            patch.object(back, "_utc_now", return_value=fixed_now),
        ):
            back._xfiles_upsert_deal(self._deal("small", "lead", 50000.0, 0.2, 0.5, 45, "Small Lead"))
            back._xfiles_upsert_deal(self._deal("best", "qualified", 800000.0, 0.6, 0.7, 82, "Best Buyer"))

            opportunities = back.api_payme_deals_opportunities(limit=10)

        self.assertEqual(opportunities.total, 2)
        self.assertEqual(opportunities.items[0].id, "best")
        self.assertEqual(opportunities.items[0].rank, 1)
        self.assertEqual(opportunities.items[0].who, "Best Buyer")
        self.assertIn("квалифицировать клиента", opportunities.items[0].need)
        self.assertIn("X-Files", opportunities.items[0].offer)
        self.assertIn("follow-up", opportunities.items[0].first_message)
        self.assertGreater(opportunities.items[0].profit_per_user_hour, opportunities.items[1].profit_per_user_hour)
        self.assertIn("когда писать", opportunities.message)


if __name__ == "__main__":
    unittest.main()
