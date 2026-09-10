from __future__ import annotations

import unittest
from unittest.mock import patch

from app.schemas.compat_models import MessageDTO
from app.services import leads


class ChatMessagesSelectorFallbackTest(unittest.TestCase):
    def test_chat_messages_resolves_selector_username_jsonl_and_before_window(self) -> None:
        messages = [
            MessageDTO(id=1, role="user", text="one", date_utc="2026-05-25T01:00:00+00:00"),
            MessageDTO(id=2, role="user", text="two", date_utc="2026-05-25T02:00:00+00:00"),
            MessageDTO(id=3, role="user", text="three", date_utc="2026-05-25T03:00:00+00:00"),
            MessageDTO(id=4, role="user", text="four", date_utc="2026-05-25T04:00:00+00:00"),
        ]

        def fake_resolve(value: str):
            normalized = str(value or "").strip().lower()
            if normalized in {"breakfast_with_harskii", "breakfast_with_harskii.jsonl"}:
                return "breakfast_with_harskii"
            return None

        def fake_read(_stem: str, offset: int = 0, limit: int = 200):
            if limit == 0:
                return list(messages)
            return list(messages)[-limit:]

        with patch.object(leads, "_resolve_lead_basename", side_effect=fake_resolve):
            with patch.object(leads, "_read_messages", side_effect=fake_read):
                latest = leads.api_payme_chat_messages(selector="@breakfast_with_harskii", limit=2)
                older = leads.api_payme_chat_messages(selector="breakfast_with_harskii.jsonl", before=4, limit=2)

        self.assertEqual([3, 4], [item.id for item in latest])
        self.assertEqual([2, 3], [item.id for item in older])


if __name__ == "__main__":
    unittest.main()
