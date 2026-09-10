import unittest
from unittest.mock import patch

import back


class OutreachValuesTest(unittest.TestCase):
    def test_message_value_keeps_full_length(self) -> None:
        full_text = "Первая строка\n" + "очень длинное сообщение " * 40
        with patch.object(back, "duckdb", None):
            item = back._outreach_item_from_payload(
                back.OutreachCrmFieldPayload(
                    field_type="message",
                    value=full_text,
                    text=full_text,
                    lead="demo",
                    date_utc="2026-04-29T08:00:00+00:00",
                )
            )

        self.assertEqual(item.value, full_text.strip())
        self.assertEqual(item.text, full_text.strip())

    def test_message_key_uses_context_not_preview_value(self) -> None:
        base = {
            "field_type": "message",
            "lead": "demo",
            "message_id": None,
            "date_utc": "2026-04-29T08:00:00+00:00",
        }

        preview_id = back._outreach_item_id({**base, "value": "короткий preview"})
        full_id = back._outreach_item_id({**base, "value": "полный текст " * 100})

        self.assertEqual(preview_id, full_id)

    def test_context_value_replaces_preview_with_full_text(self) -> None:
        full_text = "полный текст сообщения без сокращения " * 20

        self.assertEqual(
            back._outreach_expand_value_with_full_text("message", "полный текст...", "полный текст...", full_text),
            full_text.strip(),
        )
        self.assertEqual(
            back._outreach_expand_value_with_full_text("chat", "demo: полный текст...", "полный текст...", full_text),
            f"demo: {full_text.strip()}",
        )

    def test_do_not_contact_removes_contact_from_outreach_fallback_only(self) -> None:
        original_outreach = back.telegram_sync.state.get("_outreach")
        original_exclusions = back.telegram_sync.state.get(back.CONTACT_EXCLUSIONS_STATE_KEY)

        def restore() -> None:
            if original_outreach is None:
                back.telegram_sync.state.pop("_outreach", None)
            else:
                back.telegram_sync.state["_outreach"] = original_outreach
            if original_exclusions is None:
                back.telegram_sync.state.pop(back.CONTACT_EXCLUSIONS_STATE_KEY, None)
            else:
                back.telegram_sync.state[back.CONTACT_EXCLUSIONS_STATE_KEY] = original_exclusions

        self.addCleanup(restore)
        first = back.OutreachCrmFieldDTO(
            id="match",
            field_type="telegram_contact",
            field_label="Контакт",
            value="Alice",
            contact_key="contact-1",
            sender_name="Alice",
            status="new",
            created_at="2026-05-06T00:00:00+00:00",
        )
        second = back.OutreachCrmFieldDTO(
            id="keep",
            field_type="telegram_contact",
            field_label="Контакт",
            value="Bob",
            contact_key="contact-2",
            sender_name="Bob",
            status="new",
            created_at="2026-05-06T00:00:00+00:00",
        )
        back.telegram_sync.state["_outreach"] = {"crm_fields": [first.model_dump(), second.model_dump()]}
        with patch.object(back, "duckdb", None), patch.object(back.telegram_sync, "save_state", lambda: None):
            summary = back._set_contact_do_not_contact("contact-1", True, "unit test")
            removed = back._delete_outreach_items_for_contact("contact-1", {"display_name": "Alice"})

        self.assertTrue(summary["do_not_contact"])
        self.assertEqual(removed, 1)
        self.assertEqual(
            [row["id"] for row in back.telegram_sync.state["_outreach"]["crm_fields"]],
            ["keep"],
        )

    def test_crm_field_plus_keeps_full_value_and_minus_removes_it(self) -> None:
        original_outreach = back.telegram_sync.state.get("_outreach")

        def restore() -> None:
            if original_outreach is None:
                back.telegram_sync.state.pop("_outreach", None)
            else:
                back.telegram_sync.state["_outreach"] = original_outreach

        self.addCleanup(restore)
        full_value = "компания с длинным описанием " * 30
        payload = back.OutreachCrmFieldPayload(
            field_type="company",
            value=full_value,
            lead="demo",
            source_selector="demo",
            message_id=42,
            text="контекст сообщения",
        )

        with patch.object(back, "duckdb", None), patch.object(back.telegram_sync, "save_state", lambda: None):
            item = back._upsert_outreach_item(back._outreach_item_from_payload(payload))
            self.assertEqual(item.value, full_value.strip())
            self.assertTrue(back.telegram_sync.state["_outreach"]["crm_fields"])

            removed = back._delete_outreach_item(item.id)

        self.assertTrue(removed)
        self.assertEqual(back.telegram_sync.state["_outreach"]["crm_fields"], [])

    def test_source_messages_reach_outreach_with_full_text(self) -> None:
        full_text = (
            "Полный текст сообщения для enReach: "
            "здесь много деталей о потребности клиента, контексте, сроках, бюджете и следующем шаге. "
            * 8
        ).strip()
        preview = "Полный текст сообщения для enReach: здесь много деталей..."
        cases = [
            ("import", "message", "Import", preview, preview, full_text),
            ("grid", "chat", "Чат", f"demo-chat: {preview}", preview, f"demo-chat: {full_text}"),
            ("media", "media", "Media", f"communitysprints OCR: {preview}", preview, f"communitysprints OCR: {full_text}"),
            ("contacts", "message", "Сообщение", preview, preview, full_text),
            ("events", "event_message", "Мероприятие", preview, preview, full_text),
            ("jur-entities", "message", "Сообщение", preview, preview, full_text),
        ]

        with patch("back._outreach_fetch_full_message_text_sync", return_value=full_text) as fetch_mock:
            for source_name, field_type, label, value, text, expected_value in cases:
                with self.subTest(source=source_name):
                    item = back._outreach_item_from_payload(
                        back.OutreachCrmFieldPayload(
                            field_type=field_type,
                            field_label=label,
                            value=value,
                            lead=source_name,
                            source_selector=source_name,
                            message_id=1000 + len(source_name),
                            date_utc="2026-05-06T12:00:00+00:00",
                            text=text,
                        )
                    )

                    self.assertEqual(item.value, expected_value)
                    self.assertEqual(item.text, full_text)

        self.assertEqual(fetch_mock.call_count, len(cases))

    @unittest.skipIf(back.duckdb is None, "duckdb dependency is not installed")
    def test_readding_source_deduplicates_messages_by_source_and_message_id(self) -> None:
        conn = back.duckdb.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE messages_raw (
                    row_hash VARCHAR,
                    source_jsonl VARCHAR,
                    message_id BIGINT,
                    source_offset BIGINT,
                    ingested_at TIMESTAMPTZ
                )
                """
            )
            conn.executemany(
                "INSERT INTO messages_raw VALUES (?, ?, ?, ?, ?)",
                [
                    ("old-row", "out/demo.jsonl", 1001, 10, "2026-05-06T09:00:00+00:00"),
                    ("new-row", "out/demo.jsonl", 1001, 20, "2026-05-06T09:01:00+00:00"),
                    ("other-message", "out/demo.jsonl", 1002, 30, "2026-05-06T09:02:00+00:00"),
                ],
            )

            self.assertEqual(back._duckdb_duplicate_message_rows_count_sync(conn), 1)
            self.assertEqual(back._duckdb_deduplicate_messages_sync(conn), 1)
            self.assertEqual(back._duckdb_duplicate_message_rows_count_sync(conn), 0)
            rows = conn.execute("SELECT row_hash FROM messages_raw ORDER BY message_id").fetchall()
        finally:
            conn.close()

        self.assertEqual([row[0] for row in rows], ["new-row", "other-message"])

    def test_contact_signal_filters_detect_sales_fields(self) -> None:
        flags = back._contact_signal_flags({
            "display_name": "Анна",
            "latest_message_text": (
                "Нужен подрядчик для вебинара в Москве. "
                "Пишите на anna@example.com или +7 999 123-45-67. "
                "Компания ООО Ромашка."
            ),
            "deal_score": 10,
            "intent_score": 10,
        })

        self.assertTrue(flags["has_contact_data"])
        self.assertTrue(flags["has_phone"])
        self.assertTrue(flags["has_email"])
        self.assertTrue(flags["has_need"])
        self.assertTrue(flags["has_event"])
        self.assertTrue(flags["has_company"])
        self.assertTrue(flags["has_city"])

        matching = back.TelegramContactDTO(contact_key="anna", display_name="Анна", **flags)
        other = back.TelegramContactDTO(contact_key="empty", display_name="Пустой")

        filtered = back._filter_telegram_contacts_by_signals(
            [matching, other],
            signal_filter="contact,need,event,company,city",
        )

        self.assertEqual([row.contact_key for row in filtered], ["anna"])


if __name__ == "__main__":
    unittest.main()
