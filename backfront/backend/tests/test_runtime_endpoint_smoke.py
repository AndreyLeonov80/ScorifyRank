import json
import os
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

API_BASE = os.environ.get("BACKFRONT_SMOKE_API_BASE", "http://127.0.0.1:8009")
WAIT_TIMEOUT_SEC = float(os.environ.get("BACKFRONT_SMOKE_WAIT_TIMEOUT", "30"))


def _join_url(path: str, params: dict[str, object] | None = None) -> str:
    url = f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    return url


def _request_json(
    path: str,
    params: dict[str, object] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, object], str]:
    req = urllib.request.Request(_join_url(path, params), headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(body), exc.headers.get("Content-Type", "")


def _wait_until_ready() -> None:
    deadline = time.time() + WAIT_TIMEOUT_SEC
    last_error = None
    while time.time() < deadline:
        try:
            status, payload, _ = _request_json("/api/payme/server-status", timeout=5.0)
            if status == 200 and payload.get("startup_phase") == "complete":
                return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(1.0)
    raise AssertionError(f"Backend smoke API is not ready at {API_BASE}: {last_error}")


class RuntimeEndpointSmokeTest(unittest.TestCase):
    JSON_ENDPOINTS = [
        ("/api/payme/server-status", None, {200}, {"instance_id", "mode", "pid", "startup_phase"}),
        ("/api/payme/runtime-status", None, {200}, {"auth_status", "connected", "auth_step"}),
        ("/api/payme/system-metrics", {"history_points": 1}, {200}, {"ts", "cpu_percent", "tasks"}),
        ("/api/payme/duckdb/status", None, {200}, {"available", "running", "message_rows"}),
        ("/api/payme/settings", None, {200}, {"telegram_phone", "telegram_api_id"}),
        ("/api/payme/license/status", None, {200}, {"status", "features"}),
        ("/api/payme/tariffs", None, {200}, {"plans"}),
        ("/api/payme/source-policies", None, {200}, {"items"}),
        ("/api/payme/import-sync/status", None, {200}, {"enabled"}),
        ("/api/payme/routes/status", None, {200, 403}, set()),
        ("/api/payme/contacts", {"page": 1, "page_size": 1, "limit": 1}, {200, 403}, set()),
        ("/api/payme/leads", {"page": 1, "page_size": 1}, {200, 404}, set()),
    ]

    @classmethod
    def setUpClass(cls) -> None:
        _wait_until_ready()

    def test_key_json_endpoints_are_reachable(self) -> None:
        for path, params, accepted_statuses, required_keys in self.JSON_ENDPOINTS:
            with self.subTest(path=path):
                status, payload, content_type = _request_json(path, params)
                self.assertIn(status, accepted_statuses)
                self.assertIn("application/json", content_type.lower())
                self.assertIsInstance(payload, dict)
                for key in required_keys:
                    self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
