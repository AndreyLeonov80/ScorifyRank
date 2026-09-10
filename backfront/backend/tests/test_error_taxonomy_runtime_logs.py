from __future__ import annotations

from datetime import datetime, timezone
from itertools import count
from threading import Lock

from app.core.error_taxonomy import classify_error_text, recovery_hint
from app.services import runtime_status


def test_error_taxonomy_classifies_common_runtime_failures() -> None:
    cases = {
        "Telegram FloodWait 123 seconds": "floodwait",
        "Failed to fetch backend": "network",
        "PAYME_OUT_DIR state.tmp -> state.json failed": "state_write_failed",
        "DuckDB database is locked": "duckdb_locked",
        "RabbitMQ broker unavailable": "queue_unavailable",
        "OpenRouter HTTP 503": "provider_error",
        "Лимит тарифа на Telegram-источники исчерпан": "license_limit",
        "Telegram session expired, нужна авторизация": "auth_required",
    }
    for text, expected in cases.items():
        assert classify_error_text(text) == expected
        assert recovery_hint(expected)


def test_runtime_logs_attach_error_code_and_recovery_hint(monkeypatch) -> None:
    logs = []
    monkeypatch.setattr(runtime_status, "_runtime_logs", logs, raising=False)
    monkeypatch.setattr(runtime_status, "_runtime_logs_lock", Lock(), raising=False)
    monkeypatch.setattr(runtime_status, "_runtime_log_counter", count(1), raising=False)
    monkeypatch.setattr(runtime_status, "_utc_now", lambda: datetime(2026, 5, 24, tzinfo=timezone.utc), raising=False)
    monkeypatch.setattr(runtime_status, "_runtime_log_mask_pii_enabled", lambda: False, raising=False)
    monkeypatch.setattr(runtime_status, "_mask_pii_text", lambda value: value, raising=False)
    monkeypatch.setattr(runtime_status, "_prune_runtime_logs", lambda _now: None, raising=False)

    before = len(logs)
    runtime_status._append_runtime_log("duckdb", "DuckDB database is locked")
    row = logs[-1]

    assert len(logs) == before + 1
    assert row["error_code"] == "duckdb_locked"
    assert "DuckDB" in row["recovery_hint"]
