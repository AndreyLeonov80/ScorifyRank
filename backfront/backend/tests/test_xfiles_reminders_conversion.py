import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import back


class XFilesRemindersConversionTest(unittest.TestCase):
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

    def _deal(self, deal_id: str, stage: back.DealStage, next_action_at: str, profit: float) -> back.XFilesDealDTO:
        return back.XFilesDealDTO(
            id=deal_id,
            title=f"Сделка {deal_id}",
            stage=stage,
            score=70,
            expected_value=profit * 2,
            probability=0.5,
            margin=1.0,
            expected_profit=profit,
            contact_key=f"contact:{deal_id}",
            contact_name=f"Contact {deal_id}",
            source="test",
            source_chat="sales-chat",
            need="Нужно быстро квалифицировать потребность и довести до КП.",
            product_match="X-Files revenue operating system",
            next_action="Написать follow-up",
            next_action_at=next_action_at,
            created_at="2026-05-06T08:00:00+00:00",
            updated_at="2026-05-06T08:00:00+00:00",
        )

    def _outreach(self, key: str, status: back.OutreachTouchStatus) -> back.XFilesOutreachSequenceDTO:
        item = back._xfiles_create_outreach_sequence(
            back.XFilesOutreachSequencePayload(
                stable_key=key,
                title=f"Sequence {key}",
                contact_name=f"Contact {key}",
                lead="sales-chat",
                source_selector="sales-chat",
                need="Проверить интерес и назначить следующий шаг.",
                product_match="X-Files revenue operating system",
            )
        )
        updated = back._xfiles_update_outreach_touch_status(item.id, "first_touch", status)
        self.assertIsNotNone(updated)
        return updated  # type: ignore[return-value]

    def test_deal_reminders_prioritize_red_and_yellow_sla(self) -> None:
        fixed_now = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
            patch.object(back, "_utc_now", return_value=fixed_now),
        ):
            back._xfiles_upsert_deal(self._deal("red", "proposal", "2026-05-06T09:00:00+00:00", 120000.0))
            back._xfiles_upsert_deal(self._deal("yellow", "qualified", "2026-05-06T12:00:00+00:00", 60000.0))
            back._xfiles_upsert_deal(self._deal("green", "lead", "2026-05-08T10:00:00+00:00", 10000.0))
            reminders = back.api_payme_deals_reminders(limit=10)

        self.assertEqual(reminders.total, 3)
        self.assertEqual(reminders.overdue, 1)
        self.assertEqual(reminders.due_soon, 1)
        self.assertEqual(reminders.items[0].deal_id, "red")
        self.assertEqual(reminders.items[0].sla_status, "red")
        self.assertIn("Просрочено", reminders.items[0].reminder_text)
        self.assertEqual(reminders.items[1].deal_id, "yellow")
        self.assertEqual(reminders.items[1].sla_status, "yellow")
        self.assertGreater(reminders.items[0].urgency, reminders.items[2].urgency)

    def test_deal_conversion_combines_outreach_and_pipeline_metrics(self) -> None:
        fixed_now = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
            patch.object(back, "_utc_now", return_value=fixed_now),
        ):
            back._xfiles_upsert_deal(self._deal("proposal", "proposal", "2026-05-06T11:00:00+00:00", 100000.0))
            back._xfiles_upsert_deal(self._deal("qualified", "qualified", "2026-05-06T11:00:00+00:00", 50000.0))
            back._xfiles_upsert_deal(self._deal("lead", "lead", "2026-05-08T11:00:00+00:00", 30000.0))
            self._outreach("seq-sent", "sent")
            self._outreach("seq-replied", "replied")
            self._outreach("seq-meeting", "meeting_booked")
            conversion = back.api_payme_deals_conversion()

        self.assertEqual(conversion.deal_total, 3)
        self.assertEqual(conversion.active_deals, 3)
        self.assertEqual(conversion.outreach_sent, 3)
        self.assertEqual(conversion.outreach_replies, 2)
        self.assertEqual(conversion.outreach_meetings, 1)
        self.assertEqual(conversion.proposals, 1)
        self.assertEqual(conversion.reply_rate_percent, 66.7)
        self.assertEqual(conversion.meeting_rate_percent, 50.0)
        self.assertEqual(conversion.proposal_rate_percent, 33.3)
        self.assertTrue(conversion.funnel)
        self.assertIn("outReach", conversion.message)


if __name__ == "__main__":
    unittest.main()
