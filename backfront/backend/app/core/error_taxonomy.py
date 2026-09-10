"""Shared runtime error taxonomy.

The UI and logs should not need to parse arbitrary exception strings.  This
module keeps the first coarse classification pass deliberately small and stable.
"""

from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "auth_required",
    "floodwait",
    "network",
    "license_limit",
    "duckdb_locked",
    "state_write_failed",
    "queue_unavailable",
    "provider_error",
    "unknown",
]


def classify_error_text(value: object) -> ErrorCode:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    if any(marker in text for marker in ("auth_required", "session expired", "reauthorize", "authorization required", "нужна авторизация")):
        return "auth_required"
    if any(marker in text for marker in ("floodwait", "flood wait", "flood_wait", "cooldown", "too many requests")):
        return "floodwait"
    if any(marker in text for marker in ("failed to fetch", "network", "connection refused", "connection reset", "timeout", "timed out")):
        return "network"
    if any(marker in text for marker in ("license", "лиценз", "tariff", "лимит тарифа", "source limit")):
        return "license_limit"
    if any(marker in text for marker in ("duckdb", "database is locked", "lock timeout", "could not set lock", "conflict on update")):
        return "duckdb_locked"
    if any(marker in text for marker in ("state.tmp", "state.json", "state_write_failed", "rename", "replace failed")):
        return "state_write_failed"
    if any(marker in text for marker in ("rabbitmq", "redis", "queue unavailable", "broker", "celery")):
        return "queue_unavailable"
    if any(marker in text for marker in ("openrouter", "provider", "llm", "502", "503", "504")):
        return "provider_error"
    return "unknown"


def recovery_hint(error_code: ErrorCode) -> str:
    return {
        "auth_required": "Откройте setup wizard, заново авторизуйте Telegram и повторите операцию.",
        "floodwait": "Дождитесь окончания Telegram FloodWait/cooldown; worker продолжит чтение после паузы.",
        "network": "Проверьте backend container, порт API, VPN/сеть и нажмите Повторить.",
        "license_limit": "Проверьте статус лицензии и лимиты источников/сообщений; владелец может продлить или расширить лимит.",
        "duckdb_locked": "Дождитесь завершения текущего DuckDB ingest или перезапустите backend/worker без удаления данных.",
        "state_write_failed": "Проверьте права и свободное место в x-files-client-db; state пишется атомарно через state.tmp -> state.json.",
        "queue_unavailable": "Проверьте Redis/RabbitMQ и Celery workers; HTTP-страницы не должны выполнять тяжелую работу сами.",
        "provider_error": "Проверьте ключ провайдера LLM, VPN и повторите запрос позже.",
        "unknown": "Откройте runtime log и preflight report, затем повторите операцию.",
    }[error_code]
