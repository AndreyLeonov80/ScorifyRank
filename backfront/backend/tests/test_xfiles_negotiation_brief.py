import unittest
from unittest.mock import patch

import back


class XFilesNegotiationBriefTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_deals = back.telegram_sync.state.get(back.XFILES_DEALS_STATE_KEY)
        self._original_outreach = back.telegram_sync.state.get("_xfiles_outreach")
        back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = {"items": []}
        back.telegram_sync.state["_xfiles_outreach"] = {"sequences": []}
        back._xfiles_clear_deal_api_caches()

    def tearDown(self) -> None:
        if self._original_deals is None:
            back.telegram_sync.state.pop(back.XFILES_DEALS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = self._original_deals
        if self._original_outreach is None:
            back.telegram_sync.state.pop("_xfiles_outreach", None)
        else:
            back.telegram_sync.state["_xfiles_outreach"] = self._original_outreach
        back._xfiles_clear_deal_api_caches()

    def test_negotiation_brief_contains_strategy_and_objection_replies(self) -> None:
        deal = back.XFilesDealDTO(
            id="deal-brief-1",
            title="Revenue OS для отдела продаж",
            stage="negotiation",
            score=72,
            expected_value=300000.0,
            probability=0.5,
            margin=0.6,
            expected_profit=90000.0,
            contact_key="contact:brief",
            contact_name="Mikhail Shain",
            company="Brief LLC",
            source="contacts",
            source_chat="sales-chat",
            need="Нужно ускорить квалификацию лидов и не тратить часы менеджеров вручную.",
            product_match="X-Files revenue operating system",
            next_action="Согласовать пилот на 2 недели",
            created_at="2026-05-06T10:00:00+00:00",
            updated_at="2026-05-06T10:00:00+00:00",
        )
        messages = [
            back.TelegramContactMessageDTO(
                lead="sales-chat",
                source_selector="sales-chat",
                message_id=1,
                date_utc="2026-05-06T09:00:00+00:00",
                text="Нужна автоматизация продаж, но бюджет пока непонятен и дорого ошибиться.",
                sender_name="Mikhail Shain",
            ),
            back.TelegramContactMessageDTO(
                lead="sales-chat",
                source_selector="sales-chat",
                message_id=2,
                date_utc="2026-05-06T09:10:00+00:00",
                text="Хотим сначала маленький пилот и понятный результат по лидам.",
                sender_name="Mikhail Shain",
            ),
        ]

        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
            patch.object(back, "_contact_messages_for_qualification", return_value=messages),
        ):
            back._xfiles_upsert_deal(deal)
            first = back.api_payme_deal_negotiation_brief(deal.id)
            second = back.api_payme_deal_negotiation_brief(deal.id)

        self.assertEqual(first.deal_id, deal.id)
        self.assertEqual(second.deal_id, deal.id)
        self.assertEqual(first.stage, "negotiation")
        self.assertGreaterEqual(first.recommended_score, 72)
        self.assertEqual(first.source_messages, 2)
        self.assertTrue(any("Контакт:" in item for item in first.brief))
        self.assertTrue(any("маленький безопасный шаг" in item for item in first.strategy))
        self.assertIn("Mikhail", first.next_best_message)
        self.assertGreaterEqual(len(first.objection_replies), 1)
        self.assertTrue(any(item.get("reply") for item in first.objection_replies))
        self.assertTrue(first.call_agenda)
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_follow_up_sequence_is_created_from_deal_without_auto_send(self) -> None:
        deal = back.XFilesDealDTO(
            id="deal-followup-1",
            title="Пилот X-Files для продаж",
            stage="qualified",
            score=66,
            expected_value=180000.0,
            probability=0.4,
            margin=0.5,
            expected_profit=36000.0,
            contact_key="contact:followup",
            contact_name="Evgeniy",
            source="contacts",
            source_chat="cfa_club",
            need="Квалифицировать потребность и предложить безопасный пилот.",
            product_match="X-Files revenue operating system",
            next_action="Подготовить follow-up",
            created_at="2026-05-06T10:00:00+00:00",
            updated_at="2026-05-06T10:00:00+00:00",
        )

        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
        ):
            back._xfiles_upsert_deal(deal)
            first = back.api_payme_deal_follow_up_sequence(deal.id)
            second = back.api_payme_deal_follow_up_sequence(deal.id)

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertIsNotNone(first.item)
        self.assertIsNotNone(second.item)
        self.assertEqual(first.item.id, second.item.id)  # type: ignore[union-attr]
        self.assertEqual(first.item.id, f"deal_followup:{deal.id}")  # type: ignore[union-attr]
        self.assertEqual(first.item.status, "draft")  # type: ignore[union-attr]
        self.assertEqual(first.item.source_item_id, f"deal:{deal.id}")  # type: ignore[union-attr]
        self.assertTrue(str(first.item.stable_key or "").startswith("outreach_"))  # type: ignore[union-attr]
        self.assertEqual(len(first.item.touches), 4)  # type: ignore[union-attr]
        self.assertEqual(
            [touch.touch_key for touch in first.item.touches],  # type: ignore[union-attr]
            ["first_touch", "follow_up_1", "follow_up_2", "last_follow_up"],
        )
        self.assertTrue(all(touch.status == "draft" for touch in first.item.touches))  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
