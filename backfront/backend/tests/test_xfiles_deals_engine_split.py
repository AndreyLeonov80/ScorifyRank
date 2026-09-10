import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.deals_helpers.audit import estimate_llm_cost_metrics
from app.services.deals_helpers.builders import build_daily_plan_bucket, build_plan_item
from app.services.deals_helpers.repository import load_deal_items, postgres_status_message, postgres_waiting
from app.services.deals_helpers.scoring import deal_attention_hours, deal_priority, deal_profit, deal_profit_per_hour


@dataclass
class Deal:
    id: str = "deal-1"
    title: str = "Deal"
    stage: str = "qualified"
    score: int = 70
    expected_value: float = 100000.0
    expected_profit: float = 50000.0
    margin: float = 0.5
    sla_status: str = "red"
    next_action: str = ""
    next_action_at: str = "2026-05-21T10:00:00+00:00"
    created_at: str = "2026-05-20T10:00:00+00:00"
    updated_at: str = "2026-05-21T10:00:00+00:00"
    contact_key: str = "contact"
    contact_name: str = "Contact"
    company: str = "Company"
    source_chat: str = "chat"
    source_message_id: str = "42"


@dataclass
class Bucket:
    key: str
    label: str
    target: int
    count: int
    tone: str
    items: list


class XFilesDealsEngineSplitTest(unittest.TestCase):
    def test_scoring_helpers_rank_profit_and_attention(self) -> None:
        deal = Deal()

        self.assertEqual(deal_profit(deal), 50000.0)
        self.assertGreater(deal_attention_hours(deal), 0.1)
        self.assertEqual(deal_profit_per_hour(deal), round(50000.0 / deal_attention_hours(deal), 2))
        priority = deal_priority(deal, lambda _value: datetime(2026, 5, 21, tzinfo=timezone.utc))
        self.assertEqual(priority[0], 50000.0)
        self.assertEqual(priority[3], 2)

    def test_builder_helpers_create_daily_plan_bucket(self) -> None:
        deal = Deal()
        item = build_plan_item(
            deal,
            "Написать",
            attention_hours=deal_attention_hours,
            profit_per_hour=deal_profit_per_hour,
        )
        self.assertEqual(item["deal_id"], "deal-1")
        self.assertEqual(item["action"], "Написать")

        bucket = build_daily_plan_bucket(
            Bucket,
            key="contacts",
            label="10 контактов",
            target=2,
            candidates=[deal],
            action="Написать",
            plan_item=lambda row, action: build_plan_item(
                row,
                action,
                attention_hours=deal_attention_hours,
                profit_per_hour=deal_profit_per_hour,
            ),
        )
        self.assertEqual(bucket.count, 1)
        self.assertEqual(bucket.tone, "yellow")

    def test_repository_status_helpers_keep_state_fallback_messages(self) -> None:
        self.assertEqual(load_deal_items(lambda limit: [Deal(id=f"d-{limit}")], limit=7)[0].id, "d-7")
        self.assertFalse(postgres_waiting(postgres_dsn="", psycopg_module=object(), postgresql_available=False))
        self.assertTrue(postgres_waiting(postgres_dsn="postgres://db", psycopg_module=object(), postgresql_available=False))
        self.assertIn(
            "state.json",
            postgres_status_message(
                postgres_dsn="",
                psycopg_module=None,
                postgresql_available=False,
                migration_error="",
            ),
        )
        self.assertIn(
            "PostgreSQL",
            postgres_status_message(
                postgres_dsn="postgres://db",
                psycopg_module=object(),
                postgresql_available=True,
                migration_error="",
            ),
        )

    def test_audit_helper_uses_real_audit_when_available(self) -> None:
        metrics = estimate_llm_cost_metrics(
            items_count=10,
            qualified_count=2,
            audit_summary={
                "requests_total": 3,
                "input_tokens_estimate": 1000,
                "output_tokens_estimate": 200,
                "cost_estimate_usd": 0.42,
            },
        )

        self.assertEqual(metrics["audited_llm_requests"], 3)
        self.assertEqual(metrics["estimated_llm_input_tokens"], 1000)
        self.assertEqual(metrics["openrouter_spend_usd"], 0.42)
        self.assertEqual(metrics["cost_per_qualified_lead_usd"], 0.21)


if __name__ == "__main__":
    unittest.main()
