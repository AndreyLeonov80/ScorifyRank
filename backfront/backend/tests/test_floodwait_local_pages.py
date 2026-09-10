import copy
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import back


class FloodWaitLocalPagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_analysis = copy.deepcopy(back.telegram_sync.state.get("_analysis_cache"))
        self._original_deals = copy.deepcopy(back.telegram_sync.state.get(back.XFILES_DEALS_STATE_KEY))
        self._original_audit = copy.deepcopy(back.telegram_sync.state.get(back.XFILES_DEAL_AUDIT_STATE_KEY))
        back.telegram_sync.state["_analysis_cache"] = {
            "crm": {"running": False, "total_rows": 1, "last_refresh_at": "2026-05-06T10:00:00+00:00"},
            "contacts": {"running": False, "total_rows": 1, "last_refresh_at": "2026-05-06T10:00:00+00:00"},
        }
        back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = {"items": []}
        back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = {"items": []}
        back._api_snapshot_cache_clear_prefix("crm_status")
        back._api_snapshot_cache_clear_prefix("contacts_status")

    def tearDown(self) -> None:
        if self._original_analysis is None:
            back.telegram_sync.state.pop("_analysis_cache", None)
        else:
            back.telegram_sync.state["_analysis_cache"] = self._original_analysis
        if self._original_deals is None:
            back.telegram_sync.state.pop(back.XFILES_DEALS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = self._original_deals
        if self._original_audit is None:
            back.telegram_sync.state.pop(back.XFILES_DEAL_AUDIT_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = self._original_audit
        back._api_snapshot_cache_clear_prefix("crm_status")
        back._api_snapshot_cache_clear_prefix("contacts_status")

    def test_floodwait_does_not_block_local_crm_contacts_and_deals_pages(self) -> None:
        crm_rows = [
            {
                "lead": "sales-chat",
                "source_selector": "sales-chat",
                "message_id": 101,
                "date_utc": "2026-05-06T10:00:00+00:00",
                "text": "Alice ищет CRM-аудит и готова обсудить договор.",
                "sender_username": "alice",
                "sender_name": "Alice",
                "full_name": "Alice",
                "name_components_count": 1,
                "companies": ["Alice LLC"],
                "phones": ["+79990000000"],
                "emails": [],
                "city": "Москва",
                "match_sources": ["sender_name", "phone", "company", "city"],
            }
        ]
        contact_rows = [
            {
                "contact_key": "tg:42",
                "sender_id": 42,
                "sender_username": "alice",
                "sender_name": "Alice",
                "display_name": "Alice",
                "total_messages": 3,
                "first_message_at": "2026-05-06T09:00:00+00:00",
                "last_message_at": "2026-05-06T10:00:00+00:00",
                "latest_lead": "sales-chat",
                "latest_message_preview": "Alice ищет CRM-аудит",
                "latest_message_text": "Alice ищет CRM-аудит и готова обсудить договор.",
                "related_messages_count": 3,
                "leads": ["sales-chat"],
                "source_selectors": ["sales-chat"],
            }
        ]

        def analysis_rows(kind: str, limit=None):
            if kind == "crm":
                return crm_rows[: int(limit or len(crm_rows))]
            if kind == "contacts":
                return contact_rows[: int(limit or len(contact_rows))]
            return []

        flood_wait = {
            "active": True,
            "status": "cooldown",
            "remaining_sec": 900,
            "until": "2026-05-06T10:15:00+00:00",
            "can_fetch_after": "2026-05-06T10:15:00+00:00",
            "reason": "history sync",
        }

        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_duckdb_crm_ready", return_value=False),
            patch.object(back, "_duckdb_contacts_ready", return_value=False),
            patch.object(back, "_analysis_rows", side_effect=analysis_rows),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "get_global_flood_wait_status", return_value=flood_wait),
            patch.object(back.telegram_sync, "_is_global_flood_wait_active", return_value=True),
            patch.object(back.telegram_sync, "save_state", lambda: None),
        ):
            deal = back.api_payme_deals_create(
                back.XFilesDealPayload(
                    title="Alice CRM audit",
                    source="contacts",
                    contact_key="tg:42",
                    contact_name="Alice",
                    source_chat="sales-chat",
                    source_message_id="101",
                    need="Alice ищет CRM-аудит",
                    product_match="Revenue OS",
                )
            ).item

            try:
                crm_status = back.api_payme_crm_status()
                contacts_status = back.api_payme_contacts_status()
                crm_page = back.api_payme_crm_contacts(
                    page=1,
                    page_size=10,
                    limit=10,
                    lead=None,
                    query=None,
                    only_name=False,
                    only_phone=False,
                    only_email=False,
                    only_company=False,
                    only_city=False,
                    only_title=False,
                )
                contacts_page = back.api_payme_contacts(
                    page=1,
                    page_size=10,
                    limit=10,
                    query="",
                    lead="",
                    qualified_template="all",
                    lead_temperature="all",
                    signals="",
                )
                deals_page = back.api_payme_deals(page=1, page_size=10, query="", stage="", limit=10)
            except HTTPException as exc:
                self.fail(f"Local pages must not be blocked by FloodWait, got HTTP {exc.status_code}: {exc.detail}")

        self.assertIsNotNone(deal)
        self.assertEqual(crm_status.kind, "crm")
        self.assertEqual(contacts_status.kind, "contacts")
        self.assertEqual(crm_page.total, 1)
        self.assertEqual(crm_page.items[0].phones, ["+79990000000"])
        self.assertEqual(contacts_page.total, 1)
        self.assertEqual(contacts_page.items[0].contact_key, "tg:42")
        self.assertEqual(deals_page.total, 1)
        self.assertEqual(deals_page.items[0].contact_key, "tg:42")


if __name__ == "__main__":
    unittest.main()
