"""Environment-derived runtime constants for legacy compatibility."""

from __future__ import annotations

import os
from typing import Any

def _telegram_api_env_id() -> str:
    return str(
        os.environ.get("TELEGRAM_API_ID")
        or os.environ.get("TG_API_ID")
        or os.environ.get("API_ID")
        or ""
    ).strip()


def _telegram_api_env_hash() -> str:
    return str(
        os.environ.get("TELEGRAM_API_HASH")
        or os.environ.get("TG_API_HASH")
        or os.environ.get("API_HASH")
        or ""
    ).strip()


def _default_telegram_api_id() -> str:
    return str(
        _telegram_api_env_id()
        or os.environ.get("PAYME_DEFAULT_TELEGRAM_API_ID")
        or ""
    ).strip()


def _default_telegram_api_hash() -> str:
    return str(
        _telegram_api_env_hash()
        or os.environ.get("PAYME_DEFAULT_TELEGRAM_API_HASH")
        or ""
    ).strip()


def _normalize_telegram_api_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return ""
    return raw if int(raw) > 0 else ""


def _normalize_telegram_api_hash(value: Any) -> str:
    return str(value or "").strip()


API_ID = int(_default_telegram_api_id() or 0)
API_HASH = _default_telegram_api_hash()
SESSION = os.environ.get("TELEGRAM_SESSION", "tg_export_session")

#SESSION = os.environ.get(
#    "TELEGRAM_SESSION",
#    str(Path("/data") / "tg_export_session")
#)

JUR_ENTITIES_CHANNEL = (
    str(os.environ.get("PAYME_JUR_ENTITIES_CHANNEL", "baza_directorov") or "baza_directorov").strip()
    or "baza_directorov"
)
LLM_BASE_URL = os.environ.get("PAYME_LLM_URL", "http://192.168.1.49:8080")
LLM_ENDPOINT = os.environ.get("PAYME_LLM_ENDPOINT", "/v1/chat/completions")
PROJECT_NAME = "X-Files"
PROJECT_SUBTITLE = "revenue operating system & engine"
POSTGRES_DSN = (
    os.environ.get("XFILES_POSTGRES_DSN")
    or os.environ.get("PAYME_POSTGRES_DSN")
    or os.environ.get("DATABASE_URL")
    or ""
).strip()
POSTGRES_CONNECT_TIMEOUT_SEC = max(1, int(os.environ.get("XFILES_POSTGRES_CONNECT_TIMEOUT", "2") or "2"))
