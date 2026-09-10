import unittest

import back


class CrmExtractionTest(unittest.TestCase):
    def test_telemost_meeting_id_is_not_phone(self) -> None:
        text = "Встреча на 16 https://telemost.yandex.ru/j/95203149853690"
        self.assertEqual(back._crm_extract_phones(text), [])

    def test_regular_phone_still_detected_near_telemost_link(self) -> None:
        text = "Телефон +79702071873, встреча https://telemost.yandex.ru/j/95203149853690"
        self.assertEqual(back._crm_extract_phones(text), ["+79702071873"])

    def test_saved_crm_payload_drops_telemost_phone(self) -> None:
        row = {
            "text": "Встреча на 16 https://telemost.yandex.ru/j/95203149853690",
            "phones": ["+95203149853690"],
            "match_sources": ["sender_name", "phone"],
        }
        cleaned = back._crm_sanitize_contact_payload(row)
        self.assertEqual(cleaned["phones"], [])
        self.assertEqual(cleaned["match_sources"], ["sender_name"])

    def test_media_ocr_text_becomes_crm_row_with_media_source(self) -> None:
        image_path = back.APP_DIR / ".tmp" / "test_media_ocr" / "lead_a" / "media" / "42.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"not-a-real-image")
        self.addCleanup(lambda: image_path.unlink(missing_ok=True))

        row = back._crm_contact_from_media_ocr_text(
            image_path,
            "Контакт: Иван Петров, телефон +79702071873, email ivan@example.com",
        )
        self.assertIsNotNone(row)
        self.assertIn("+79702071873", row.phones)
        self.assertIn("ivan@example.com", row.emails)
        self.assertIn("media", row.match_sources)
        self.assertIn("ocr", row.match_sources)
        self.assertTrue(any("media.ocr" in item for values in row.field_provenance.values() for item in values))

    def test_crm_field_provenance_is_recorded(self) -> None:
        row = back._crm_extract_contact_from_record(
            "demo",
            "demo",
            {
                "sender": {"username": "ivan", "name": "Иван Петров"},
                "message": {
                    "id": 7,
                    "date_utc": "2026-04-30T10:00:00+00:00",
                    "text": "Я директор ООО Ромашка, телефон +79702071873, email ivan@example.com, Москва",
                },
            },
        )
        self.assertIsNotNone(row)
        self.assertIn("fio", row.field_provenance)
        self.assertIn("company", row.field_provenance)
        self.assertIn("phone", row.field_provenance)
        self.assertIn("email", row.field_provenance)
        self.assertIn("city", row.field_provenance)
        self.assertTrue(any("telegram.sender.name" in item for item in row.field_provenance["fio"]))

    def test_contact_summary_provenance_is_recorded(self) -> None:
        summary = back._decorate_contact_summary_with_provenance(
            {
                "contact_key": "id:123",
                "leads": ["demo"],
                "source_selectors": ["@demo"],
                "latest_lead": "demo",
                "last_message_at": "2026-04-30T10:00:00+00:00",
                "latest_message_text": "Привет",
            }
        )
        provenance = summary["provenance"]
        self.assertEqual(provenance["contact_key"]["strategy"], "telegram.sender.id")
        self.assertEqual(provenance["sources"][0]["lead"], "demo")
        self.assertEqual(provenance["latest_message"]["text_source"], "telegram.message.text")


if __name__ == "__main__":
    unittest.main()
