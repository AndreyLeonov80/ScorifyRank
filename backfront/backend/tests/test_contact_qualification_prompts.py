import unittest
from unittest.mock import patch

import back


class ContactQualificationPromptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_qualifications = back.telegram_sync.state.get(back.CONTACT_QUALIFICATIONS_STATE_KEY)
        self._original_llm_audit = back.telegram_sync.state.get(back.XFILES_LLM_AUDIT_STATE_KEY)

    def tearDown(self) -> None:
        if self._original_qualifications is None:
            back.telegram_sync.state.pop(back.CONTACT_QUALIFICATIONS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.CONTACT_QUALIFICATIONS_STATE_KEY] = self._original_qualifications
        if self._original_llm_audit is None:
            back.telegram_sync.state.pop(back.XFILES_LLM_AUDIT_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY] = self._original_llm_audit

    def test_legacy_prompt_settings_get_product_offer_prompt(self) -> None:
        legacy_prompts = [
            {
                "id": "needs_priority",
                "title": "Потребности и покупки",
                "prompt": "проанализируй сообщения человека и оцени его потребности",
            },
            {
                "id": "first_message",
                "title": "Первое сообщение для знакомства",
                "prompt": "оцени первое сообщение для знакомства",
            },
        ]

        prompts = back._coerce_contact_qualification_prompts(legacy_prompts)
        prompt_ids = [item["id"] for item in prompts]

        self.assertIn("needs_priority", prompt_ids)
        self.assertIn("first_message", prompt_ids)
        self.assertIn("product_offer", prompt_ids)

    def test_contact_summary_exposes_product_offer_result(self) -> None:
        contact_key = "unit-test-contact"
        original = back.telegram_sync.state.get(back.CONTACT_QUALIFICATIONS_STATE_KEY)
        self.addCleanup(lambda: back.telegram_sync.state.__setitem__(back.CONTACT_QUALIFICATIONS_STATE_KEY, original or {}))
        back.telegram_sync.state[back.CONTACT_QUALIFICATIONS_STATE_KEY] = {
            contact_key: {
                "product_offer": {
                    "template_id": "product_offer",
                    "status": "ready",
                    "result_text": "Предложить диагностику продаж и CRM-воронки.",
                    "model": "test-model",
                    "updated_at": "2026-05-05T10:00:00+00:00",
                }
            }
        }

        summary = back._contact_qualification_summary(contact_key)

        self.assertEqual(summary["product_offer_suggestion"], "Предложить диагностику продаж и CRM-воронки.")
        self.assertEqual(summary["product_offer_model"], "test-model")

    def test_openrouter_payload_masks_phone_and_email_by_default(self) -> None:
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "user",
                    "content": "Телефон +79991234567, email ivan.petrov@example.com, сообщение для анализа.",
                }
            ],
        }

        with patch("back._get_app_settings", return_value={"openrouter_allow_pii": False}):
            sanitized = back._sanitize_openrouter_payload_for_pii(payload)

        content = sanitized["messages"][0]["content"]
        self.assertNotIn("+79991234567", content)
        self.assertNotIn("ivan.petrov@example.com", content)
        self.assertIn("[phone masked]", content)
        self.assertIn("[email masked]", content)

    def test_openrouter_payload_can_keep_pii_when_explicitly_allowed(self) -> None:
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Телефон +79991234567"}],
        }

        with patch("back._get_app_settings", return_value={"openrouter_allow_pii": True}):
            sanitized = back._sanitize_openrouter_payload_for_pii(payload)

        self.assertIn("+79991234567", sanitized["messages"][0]["content"])

    def test_openrouter_mock_returns_contact_qualification_without_network(self) -> None:
        class FakeOpenRouterResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "id": "chatcmpl-unit-test",
                    "choices": [
                        {
                            "message": {
                                "content": "Потребность: купить аналитику продаж. Первое действие: предложить короткий аудит."
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 120,
                        "completion_tokens": 30,
                        "total_tokens": 150,
                    },
                }

        contact_key = "id:100500"
        prompt = {
            "id": "needs_priority",
            "title": "Потребности и покупки",
            "prompt": "оцени потребности",
        }
        settings = {
            "openrouter_api_key": "sk-test",
            "openrouter_model": "openai/gpt-oss-120b:free",
            "openrouter_temperature": 0.2,
            "openrouter_top_p": 0.9,
            "openrouter_max_tokens": 512,
            "openrouter_frequency_penalty": 0.0,
            "openrouter_presence_penalty": 0.0,
            "openrouter_allow_pii": False,
            "contact_qualification_prompts": [prompt],
        }
        messages = [
            back.TelegramContactMessageDTO(
                lead="demo",
                source_selector="demo",
                message_id=7,
                date_utc="2026-05-06T10:00:00+00:00",
                text="Ищу способ быстрее квалифицировать лидов и понять, кому писать первым.",
                sender_id=100500,
                sender_username="buyer",
                sender_name="Buyer",
            )
        ]

        with (
            patch("back._get_app_settings", return_value=settings),
            patch("back._duckdb_contacts_ready", return_value=False),
            patch("back._analysis_rows", return_value=[
                {
                    "contact_key": contact_key,
                    "display_name": "Buyer",
                    "sender_id": 100500,
                    "sender_username": "buyer",
                }
            ]),
            patch("back._contact_messages_for_qualification", return_value=messages),
            patch("back.telegram_sync.save_state", lambda: None),
            patch("back.requests.post", return_value=FakeOpenRouterResponse()) as request_mock,
        ):
            result = back.api_payme_contact_qualify(
                contact_key,
                back.ContactQualificationRequestDTO(template_id="needs_priority", force=True),
            )

        self.assertEqual(result.status, "ready")
        self.assertFalse(result.cache_hit)
        self.assertEqual(result.messages_count, 1)
        self.assertIn("аналитику продаж", result.result_text)
        self.assertEqual(result.model, "openai/gpt-oss-120b:free")
        self.assertEqual(request_mock.call_count, 1)
        state_item = back.telegram_sync.state[back.CONTACT_QUALIFICATIONS_STATE_KEY][contact_key]["needs_priority"]
        self.assertEqual(state_item["result_text"], result.result_text)
        audit_items = back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY]["items"]
        self.assertEqual(audit_items[0]["kind"], "contact_qualification")
        self.assertEqual(audit_items[0]["status"], "ready")

    def test_contact_with_new_messages_refreshes_qualification_incrementally(self) -> None:
        class FakeOpenRouterResponse:
            def __init__(self, content: str) -> None:
                self._content = content

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "choices": [{"message": {"content": self._content}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                }

        contact_key = "id:incremental"
        prompt = {
            "id": "needs_priority",
            "title": "Потребности и покупки",
            "prompt": "оцени потребности",
        }
        settings = {
            "openrouter_api_key": "sk-test",
            "openrouter_model": "openai/gpt-oss-120b:free",
            "openrouter_temperature": 0.2,
            "openrouter_top_p": 0.9,
            "openrouter_max_tokens": 512,
            "openrouter_frequency_penalty": 0.0,
            "openrouter_presence_penalty": 0.0,
            "openrouter_allow_pii": False,
            "contact_qualification_prompts": [prompt],
        }
        first_message = back.TelegramContactMessageDTO(
            lead="demo",
            source_selector="demo",
            message_id=1,
            date_utc="2026-05-06T10:00:00+00:00",
            text="Нужен быстрый способ находить горячих лидов.",
            sender_id=42,
            sender_username="buyer",
            sender_name="Buyer",
        )
        new_message = back.TelegramContactMessageDTO(
            lead="demo",
            source_selector="demo",
            message_id=2,
            date_utc="2026-05-06T10:05:00+00:00",
            text="Еще важно понять, кому писать первым и какой оффер предложить.",
            sender_id=42,
            sender_username="buyer",
            sender_name="Buyer",
        )
        back.telegram_sync.state[back.CONTACT_QUALIFICATIONS_STATE_KEY] = {}
        back.telegram_sync.state[back.XFILES_LLM_AUDIT_STATE_KEY] = {"items": []}

        with (
            patch("back._get_app_settings", return_value=settings),
            patch("back._duckdb_contacts_ready", return_value=False),
            patch("back._analysis_rows", return_value=[
                {
                    "contact_key": contact_key,
                    "display_name": "Buyer",
                    "sender_id": 42,
                    "sender_username": "buyer",
                }
            ]),
            patch(
                "back._contact_messages_for_qualification",
                side_effect=[[first_message], [first_message], [first_message, new_message]],
            ),
            patch("back.telegram_sync.save_state", lambda: None),
            patch(
                "back.requests.post",
                side_effect=[
                    FakeOpenRouterResponse("Версия 1: человеку нужна лидогенерация."),
                    FakeOpenRouterResponse("Версия 2: лидогенерация плюс приоритизация офферов."),
                ],
            ) as request_mock,
        ):
            first_result = back.api_payme_contact_qualify(
                contact_key,
                back.ContactQualificationRequestDTO(template_id="needs_priority", force=False),
            )
            cached_result = back.api_payme_contact_qualify(
                contact_key,
                back.ContactQualificationRequestDTO(template_id="needs_priority", force=False),
            )
            refreshed_result = back.api_payme_contact_qualify(
                contact_key,
                back.ContactQualificationRequestDTO(template_id="needs_priority", force=False),
            )

        self.assertFalse(first_result.cache_hit)
        self.assertEqual(first_result.messages_count, 1)
        self.assertTrue(cached_result.cache_hit)
        self.assertEqual(cached_result.result_text, first_result.result_text)
        self.assertFalse(refreshed_result.cache_hit)
        self.assertEqual(refreshed_result.messages_count, 2)
        self.assertIn("приоритизация", refreshed_result.result_text)
        self.assertEqual(request_mock.call_count, 2)
        state_item = back.telegram_sync.state[back.CONTACT_QUALIFICATIONS_STATE_KEY][contact_key]["needs_priority"]
        self.assertEqual(state_item["result_text"], refreshed_result.result_text)
        self.assertEqual(state_item["messages_count"], 2)


if __name__ == "__main__":
    unittest.main()
