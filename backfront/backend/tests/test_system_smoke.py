import json
import os
import time
import unittest
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple


API_BASE = os.environ.get("PAYME_TEST_API_BASE", "http://127.0.0.1:8000")
WEB_BASE = os.environ.get("PAYME_TEST_WEB_BASE", "http://localhost:8001")
WAIT_TIMEOUT_SEC = float(os.environ.get("PAYME_TEST_WAIT_TIMEOUT", "30"))


def _join_url(base: str, path: str, params: Optional[Dict[str, object]] = None) -> str:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}?{query}"
    return url


def _request(url: str, timeout: float = 10.0) -> Tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, body, response.headers.get("Content-Type", "")


def _json_request(url: str, payload: Optional[Dict[str, object]] = None, method: str = "POST", timeout: float = 10.0) -> Tuple[int, str, str]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
        return response.status, text, response.headers.get("Content-Type", "")


def _read_stream_probe(url: str, timeout: float = 20.0) -> Tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for _ in range(10):
            line = response.readline().decode("utf-8", errors="replace").strip()
            if line:
                return response.status, response.headers.get("Content-Type", ""), line
        raise AssertionError(f"Не удалось получить ни одного SSE-события или heartbeat из {url}")


def _wait_until_ready(url: str, timeout_sec: float) -> None:
    deadline = time.time() + timeout_sec
    last_error = None
    while time.time() < deadline:
        try:
            status, _, _ = _request(url, timeout=5.0)
            if 200 <= status < 500:
                return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(1.0)
    raise AssertionError(f"Сервис не стал доступен вовремя: {url}. Последняя ошибка: {last_error}")


class PaymeSystemSmokeTest(unittest.TestCase):
    WEB_PAGES = [
        ("/", "Ai Agents Chats"),
        ("/grid.html", "Sync"),
        ("/media.html", "Media"),
        ("/contacts.html", "Контакты"),
        ("/crm.html", "CRM"),
        ("/outreach.html", "outReach"),
        ("/events.html", "Мероприятия"),
        ("/import.html", "Импорт из Telegram"),
        ("/logs.html", "Логи"),
    ]

    JSON_ENDPOINTS = [
        ("/api/payme/runtime-status", None, ["auth_status", "connected"]),
        ("/api/payme/server-status", None, ["instance_id", "mode", "pid", "uptime_sec"]),
        ("/api/payme/leads", {"page": 1, "page_size": 10}, ["items", "total", "page", "page_size", "total_pages"]),
        ("/api/payme/media/config", None, ["selected_leads"]),
        ("/api/payme/event-keywords", None, ["keywords"]),
        ("/api/payme/import-sync/status", None, ["enabled"]),
        ("/api/payme/contacts", {"page": 1, "page_size": 10, "limit": 10}, ["items", "total"]),
        ("/api/payme/crm/contacts", {"page": 1, "page_size": 10, "limit": 10}, ["items", "total"]),
        ("/api/payme/outreach/items", {"page": 1, "page_size": 10}, ["items", "total", "page", "page_size", "total_pages"]),
    ]

    @classmethod
    def setUpClass(cls) -> None:
        _wait_until_ready(_join_url(API_BASE, "/api/payme/runtime-status"), WAIT_TIMEOUT_SEC)
        _wait_until_ready(_join_url(WEB_BASE, "/"), WAIT_TIMEOUT_SEC)

    def test_web_pages_are_served(self) -> None:
        for path, expected_text in self.WEB_PAGES:
            with self.subTest(path=path):
                status, body, content_type = _request(_join_url(WEB_BASE, path))
                self.assertEqual(status, 200)
                self.assertIn("text/html", content_type.lower())
                self.assertIn(expected_text, body)

    def test_json_endpoints_are_alive(self) -> None:
        for path, params, required_keys in self.JSON_ENDPOINTS:
            with self.subTest(path=path):
                status, body, content_type = _request(_join_url(API_BASE, path, params))
                self.assertEqual(status, 200)
                self.assertIn("application/json", content_type.lower())
                payload = json.loads(body)
                if required_keys:
                    for key in required_keys:
                        self.assertIn(key, payload)

    def test_runtime_status_is_consistent(self) -> None:
        _, body, _ = _request(_join_url(API_BASE, "/api/payme/runtime-status"))
        payload = json.loads(body)
        self.assertIn(payload["auth_status"], {"authorized", "needs_api_credentials", "needs_auth", "session_present", "unknown"})
        self.assertIn(payload["auth_step"], {"api", "phone", "code", "password", "done"})
        self.assertIsInstance(payload["connected"], bool)

    def test_server_status_contract(self) -> None:
        _, body, _ = _request(_join_url(API_BASE, "/api/payme/server-status"))
        payload = json.loads(body)
        self.assertIn(payload["mode"], {"docker", "local"})
        self.assertIsInstance(payload["instance_id"], str)
        self.assertGreater(len(payload["instance_id"]), 0)
        self.assertIsInstance(payload["pid"], int)
        self.assertGreaterEqual(payload["uptime_sec"], 0)

    def test_leads_and_messages_contract(self) -> None:
        _, body, _ = _request(_join_url(API_BASE, "/api/payme/leads", {"page": 1, "page_size": 10}))
        payload = json.loads(body)
        self.assertIsInstance(payload, dict)
        self.assertIn("items", payload)
        self.assertIsInstance(payload["items"], list)
        self.assertGreater(len(payload["items"]), 0, "Ожидался хотя бы один чат в системе")

        first_lead = payload["items"][0]
        self.assertIn("name", first_lead)
        self.assertIn("count", first_lead)
        self.assertIn("sync_status", first_lead)

        _, msg_body, msg_ct = _request(
            _join_url(
                API_BASE,
                f"/api/payme/leads/{urllib.parse.quote(first_lead['name'])}/messages",
                {"limit": 5},
            )
        )
        self.assertIn("application/json", msg_ct.lower())
        messages = json.loads(msg_body)
        self.assertIsInstance(messages, list)
        for message in messages:
            self.assertIn("id", message)
            self.assertIn("text", message)
            self.assertIn("date_utc", message)

    def test_crm_endpoint_contract(self) -> None:
        _, body, _ = _request(_join_url(API_BASE, "/api/payme/crm/contacts", {"page": 1, "page_size": 10, "limit": 20}))
        payload = json.loads(body)
        self.assertIsInstance(payload, dict)
        rows = payload.get("items", [])
        self.assertIsInstance(rows, list)
        for row in rows[:5]:
            self.assertIn("lead", row)
            self.assertIn("message_id", row)
            self.assertIn("date_utc", row)
            self.assertIn("text", row)
            self.assertIn("companies", row)
            self.assertIn("phones", row)
            self.assertIn("emails", row)
            self.assertIn("match_sources", row)

    def test_outreach_crm_field_roundtrip(self) -> None:
        payload = {
            "field_type": "contact",
            "field_label": "Контакты",
            "value": "+70000000000",
            "lead": "smoke-test",
            "source_selector": "smoke-test",
            "message_id": 1,
            "date_utc": "2026-01-01T00:00:00+00:00",
            "text": "smoke outreach item",
            "sender_username": "smoke_sender",
            "sender_name": "Smoke Sender",
        }
        status, body, content_type = _json_request(_join_url(API_BASE, "/api/payme/outreach/items"), payload)
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type.lower())
        created = json.loads(body)
        self.assertTrue(created.get("ok"))
        item = created.get("item") or {}
        self.assertEqual(item.get("value"), payload["value"])
        self.assertEqual(item.get("field_type"), "contact")

        _, list_body, _ = _request(_join_url(API_BASE, "/api/payme/outreach/items", {"query": payload["value"], "page": 1, "page_size": 10}))
        listed = json.loads(list_body)
        self.assertGreaterEqual(listed.get("total", 0), 1)

        item_id = urllib.parse.quote(str(item["id"]), safe="")
        status, deleted_body, _ = _json_request(_join_url(API_BASE, f"/api/payme/outreach/items/{item_id}"), None, method="DELETE")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(deleted_body).get("ok"))

    def test_outreach_generic_field_type_roundtrip(self) -> None:
        payload = {
            "field_type": "event_message",
            "field_label": "Мероприятие",
            "value": "smoke event outreach item",
            "lead": "smoke-events",
            "source_selector": "smoke-events",
            "message_id": 2,
            "date_utc": "2026-01-01T00:00:01+00:00",
            "text": "smoke event outreach item",
            "sender_username": "smoke_sender",
            "sender_name": "Smoke Sender",
        }
        status, body, content_type = _json_request(_join_url(API_BASE, "/api/payme/outreach/items"), payload)
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type.lower())
        created = json.loads(body)
        self.assertTrue(created.get("ok"))
        item = created.get("item") or {}
        self.assertEqual(item.get("field_type"), "event_message")
        self.assertEqual(item.get("field_label"), "Мероприятие")

        item_id = urllib.parse.quote(str(item["id"]), safe="")
        status, deleted_body, _ = _json_request(_join_url(API_BASE, f"/api/payme/outreach/items/{item_id}"), None, method="DELETE")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(deleted_body).get("ok"))

    def test_contacts_endpoint_contract(self) -> None:
        _, body, _ = _request(_join_url(API_BASE, "/api/payme/contacts", {"page": 1, "page_size": 10, "limit": 20}))
        payload = json.loads(body)
        self.assertIsInstance(payload, dict)
        rows = payload.get("items", [])
        self.assertIsInstance(rows, list)
        for row in rows[:5]:
            self.assertIn("contact_key", row)
            self.assertIn("display_name", row)
            self.assertIn("total_messages", row)
            self.assertIn("leads", row)
            self.assertIn("related_messages", row)
        if rows:
            contact_key = urllib.parse.quote(rows[0]["contact_key"], safe="")
            _, messages_body, _ = _request(
                _join_url(API_BASE, f"/api/payme/contacts/{contact_key}/messages", {"page": 1, "page_size": 10})
            )
            messages_payload = json.loads(messages_body)
            self.assertIsInstance(messages_payload, dict)
            self.assertIn("items", messages_payload)

    def test_global_sse_stream_is_alive(self) -> None:
        status, content_type, line = _read_stream_probe(_join_url(API_BASE, "/api/payme/stream/leads"))
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", content_type.lower())
        self.assertTrue(
            line.startswith(":") or line.startswith("data:"),
            f"Ожидался SSE heartbeat или data event, получено: {line!r}",
        )

    def test_runtime_logs_sse_stream_is_alive(self) -> None:
        status, content_type, line = _read_stream_probe(_join_url(API_BASE, "/api/payme/runtime-logs/stream"))
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", content_type.lower())
        self.assertTrue(
            line.startswith(":") or line.startswith("data:"),
            f"Ожидался SSE heartbeat или data event, получено: {line!r}",
        )

    def test_lead_sse_stream_is_alive(self) -> None:
        _, body, _ = _request(_join_url(API_BASE, "/api/payme/leads", {"page": 1, "page_size": 10}))
        payload = json.loads(body)
        leads = payload.get("items", [])
        self.assertGreater(len(leads), 0, "Ожидался хотя бы один чат для проверки lead stream")

        probe_lead = next((lead for lead in leads if lead.get("has_jsonl")), leads[0])
        stream_url = _join_url(
            API_BASE,
            f"/api/payme/leads/{urllib.parse.quote(probe_lead['name'])}/stream",
        )
        status, content_type, line = _read_stream_probe(stream_url)
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", content_type.lower())
        self.assertTrue(
            line.startswith(":") or line.startswith("data:"),
            f"Ожидался SSE heartbeat или data event, получено: {line!r}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
