import unittest
from unittest.mock import patch

import back


class XFilesDealSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_deals = back.telegram_sync.state.get(back.XFILES_DEALS_STATE_KEY)
        self._original_audit = back.telegram_sync.state.get(back.XFILES_DEAL_AUDIT_STATE_KEY)
        self._original_outreach = back.telegram_sync.state.get("_outreach")
        back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = {"items": []}
        back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = {"items": []}
        back.telegram_sync.state["_outreach"] = {"crm_fields": []}

    def tearDown(self) -> None:
        if self._original_deals is None:
            back.telegram_sync.state.pop(back.XFILES_DEALS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = self._original_deals
        if self._original_audit is None:
            back.telegram_sync.state.pop(back.XFILES_DEAL_AUDIT_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = self._original_audit
        if self._original_outreach is None:
            back.telegram_sync.state.pop("_outreach", None)
        else:
            back.telegram_sync.state["_outreach"] = self._original_outreach

    def test_deal_can_be_created_from_contact_crm_enreach_and_event(self) -> None:
        payloads = [
            back.XFilesDealPayload(
                title="Контакт: Alice",
                source="contacts",
                contact_key="contact:alice",
                contact_name="Alice",
                need="Обсудить диагностику отдела продаж",
                product_match="CRM-аудит",
                next_action="Написать первое сообщение",
            ),
            back.XFilesDealPayload(
                title="CRM: телефон Alice",
                source="crm",
                source_chat="sales-chat",
                source_message_id="101",
                contact_key="contact:alice",
                contact_name="Alice",
                need="Есть телефон и компания из CRM-поля",
                product_match="Воронка продаж",
            ),
            back.XFilesDealPayload(
                title="Мероприятие: встреча с Alice",
                source="events",
                source_chat="events-chat",
                source_message_id="202",
                contact_key="contact:alice",
                contact_name="Alice",
                need="Познакомиться на мероприятии",
                product_match="Лидогенерация",
            ),
        ]

        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
        ):
            created = [back.api_payme_deals_create(payload).item for payload in payloads]
            outreach_item = back._upsert_outreach_item(
                back._outreach_item_from_payload(
                    back.OutreachCrmFieldPayload(
                        field_type="message",
                        field_label="Сообщение",
                        value="Полное сообщение из enReach о покупке аналитики продаж",
                        lead="enreach-chat",
                        source_selector="enreach-chat",
                        message_id=303,
                        date_utc="2026-05-06T10:00:00+00:00",
                        text="Полное сообщение из enReach о покупке аналитики продаж",
                        sender_name="Alice",
                    )
                )
            )
            enreach_deal = back.api_payme_deals_from_outreach(outreach_item.id).item

        all_deals = [item for item in [*created, enreach_deal] if item is not None]
        self.assertEqual(len(all_deals), 4)
        self.assertEqual({item.stage for item in all_deals}, {"lead"})
        self.assertEqual(
            {item.source for item in all_deals},
            {"contacts", "crm", "events", "enReach"},
        )
        self.assertEqual(enreach_deal.source_chat, "enreach-chat")  # type: ignore[union-attr]
        self.assertEqual(enreach_deal.source_message_id, "303")  # type: ignore[union-attr]
        self.assertIn("аналитики продаж", enreach_deal.need or "")  # type: ignore[union-attr]
        self.assertEqual(len(back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY]["items"]), 4)

    def test_deal_stage_update_keeps_payload_and_writes_audit_history(self) -> None:
        payload = back.XFilesDealPayload(
            title="Сделка: аудит продаж",
            source="contacts",
            contact_key="contact:bob",
            contact_name="Bob",
            company="Bob LLC",
            need="Нужен быстрый аудит воронки",
            product_match="Revenue OS",
            expected_value=250000.0,
            probability=0.25,
            next_action="Квалифицировать бюджет",
        )

        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
        ):
            created = back.api_payme_deals_create(payload).item
            self.assertIsNotNone(created)

            updated = back.api_payme_deals_update(
                created.id,  # type: ignore[union-attr]
                back.XFilesDealPatchPayload(
                    stage="qualified",
                    score=70,
                    probability=0.6,
                    next_action="Подготовить КП",
                ),
            ).item
            audit = back._xfiles_load_deal_audit(limit=10)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.id, created.id)  # type: ignore[union-attr]
        self.assertEqual(updated.stage, "qualified")  # type: ignore[union-attr]
        self.assertEqual(updated.contact_key, "contact:bob")  # type: ignore[union-attr]
        self.assertEqual(updated.company, "Bob LLC")  # type: ignore[union-attr]
        self.assertEqual(updated.need, "Нужен быстрый аудит воронки")  # type: ignore[union-attr]
        self.assertEqual(updated.product_match, "Revenue OS")  # type: ignore[union-attr]
        self.assertEqual(updated.expected_value, 250000.0)  # type: ignore[union-attr]
        self.assertEqual(updated.next_action, "Подготовить КП")  # type: ignore[union-attr]

        update_audit = next(item for item in audit if item.action == "update")
        create_audit = next(item for item in audit if item.action == "create")
        self.assertEqual(update_audit.deal_id, created.id)  # type: ignore[union-attr]
        self.assertEqual(update_audit.before_stage, "lead")
        self.assertEqual(update_audit.after_stage, "qualified")
        self.assertEqual(update_audit.changes.get("stage"), "qualified")
        self.assertEqual(create_audit.after_stage, "lead")


if __name__ == "__main__":
    unittest.main()
