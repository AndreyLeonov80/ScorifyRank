#uvicorn main_fastapi:app --host 0.0.0.0 --port 8000 --reload

import asyncio
import base64
import builtins
import imaplib
import hashlib
import hmac
import logging
import errno
import smtplib
import ssl
import html
import json
import os
import random
import re
import resource
import shutil
import sqlite3
import socket
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email import policy
from email.parser import BytesParser
from itertools import count
from pathlib import Path
from urllib.parse import urlencode
from typing import Any, Dict, Iterable, List, Literal, Optional, Set, Union
from uuid import uuid4

import requests
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jur_entities_structure import analyze_jur_entity_structures
from pydantic import BaseModel, Field
from security import LicenseNetworkError, check_license
from app.core.telethon_compat import TelegramClient, events
from app.core.api_errors import (
    api_error_payload,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.telethon_compat import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    PasswordHashInvalidError,
    PeerFloodError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    UserPrivacyRestrictedError,
)
from app.core.telethon_compat import TelegramMessage
from x_files_license.core import (
    LICENSE_SCHEMA as XFILES_LICENSE_SCHEMA,
    LicenseError as XFilesLicenseError,
    append_license_audit_record as xfiles_append_license_audit_record,
    apply_license as xfiles_apply_license,
    build_activation_receipt as xfiles_build_activation_receipt,
    build_license_audit_record as xfiles_build_license_audit_record,
    build_instance_hash as xfiles_build_instance_hash,
    compute_effective_allowed_menus as xfiles_compute_effective_allowed_menus,
    license_status as xfiles_license_status,
    read_license_audit_records as xfiles_read_license_audit_records,
    refresh_license_server_status as xfiles_refresh_license_server_status,
    verify_signed_document as xfiles_verify_signed_document,
)
from app.core.menu_catalog import (
    XFILES_API_MENU_PREFIXES,
    XFILES_CLIENT_DELIVERY_HIDDEN_MENU_KEYS,
    XFILES_CLIENT_DELIVERY_MENU_KEYS,
    XFILES_DEFAULT_DISABLED_MENU_KEYS,
    XFILES_HTML_MENU_PATHS,
    XFILES_LICENSE_BLOCKED_STATUSES,
    XFILES_LICENSE_FALLBACK_MENU_KEYS,
    XFILES_LICENSE_PUBLIC_API_PATHS,
    XFILES_LICENSE_PUBLIC_API_PREFIXES,
    XFILES_LICENSE_RENEWAL_MENU_KEYS,
    XFILES_LICENSE_RENEWAL_PUBLIC_HTML,
    XFILES_MENU_CATALOG,
)
from app.core.runtime_env import (
    API_HASH,
    API_ID,
    JUR_ENTITIES_CHANNEL,
    LLM_BASE_URL,
    LLM_ENDPOINT,
    POSTGRES_CONNECT_TIMEOUT_SEC,
    POSTGRES_DSN,
    PROJECT_NAME,
    PROJECT_SUBTITLE,
    SESSION,
    _default_telegram_api_hash,
    _default_telegram_api_id,
    _telegram_api_env_hash,
    _telegram_api_env_id,
    _normalize_telegram_api_hash,
    _normalize_telegram_api_id,
)
from app.core.runtime_paths import (
    APP_DIR,
    CACHE_DIR,
    DUCKDB_DIR,
    DUCKDB_PATH,
    JUR_ENTITIES_DIR,
    LEGACY_CACHE_ARCHIVE_DIR,
    LEGACY_PAYME_OUT_DIRS,
    LLM_SYSTEM_PROMPT_PATH,
    LLM_TEMPLATE_PATH,
    PARQUET_DIR,
    PAYME_OUT_DIR,
    STATE_PATH,
)
from app.core.file_stats import (
    count_glob_files as _count_glob_files,
    safe_file_size as _safe_file_size,
    sum_glob_file_sizes as _sum_glob_file_sizes,
)
from app.core.runtime_state import clear_unique_directory_contents, preserve_state_keys, safe_clear_directory_contents
from app.core.state import load_json_object
from x_files_license.tariffs import tariff_catalog as xfiles_tariff_catalog
from x_files_license.tariffs import license_capabilities as xfiles_license_capabilities
from x_files_license.tariffs import tariff_plan as xfiles_tariff_plan

try:
    import duckdb  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    duckdb = None

try:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psycopg = None
    dict_row = None

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


POSTGRES_ENABLED = bool(POSTGRES_DSN) and psycopg is not None

app = FastAPI(title=f"{PROJECT_NAME} API", version="1.2.0")
XFILES_PUBLIC_ERROR_MESSAGE = "Внутренняя ошибка сервера. Детали сохранены в backend-логе."

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _apply_browser_response_headers(request: Request, response: Response) -> Response:
    origin = request.headers.get("origin")
    if origin:
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault(
            "Access-Control-Allow-Methods",
            "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT",
        )
        response.headers.setdefault(
            "Access-Control-Allow-Headers",
            request.headers.get("access-control-request-headers") or "*",
        )

    path = request.url.path or "/"
    is_api = path.startswith("/api/payme/")
    is_shell = path == "/" or path.endswith(".html") or path.endswith(".js") or path.endswith(".css")
    if is_api or is_shell:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.exception_handler(Exception)
async def _xfiles_safe_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = uuid.uuid4().hex[:12]
    logging.getLogger("xfiles.runtime").exception(
        "Unhandled API error request_id=%s path=%s",
        request_id,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content=api_error_payload(XFILES_PUBLIC_ERROR_MESSAGE, request_id=request_id),
    )


@app.exception_handler(HTTPException)
async def _xfiles_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _xfiles_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return await validation_exception_handler(request, exc)


@app.middleware("http")
async def _disable_stale_browser_cache(request: Request, call_next):
    if request.method == "OPTIONS" and request.headers.get("origin"):
        return _apply_browser_response_headers(request, Response(status_code=204))

    renewal_only = _xfiles_renewal_only_response(request)
    if renewal_only:
        return _apply_browser_response_headers(request, renewal_only)

    telegram_setup_redirect = await _telegram_setup_wizard_redirect_response(request)
    if telegram_setup_redirect:
        return _apply_browser_response_headers(request, telegram_setup_redirect)

    denied = _xfiles_api_menu_denial(request)
    if denied:
        return _apply_browser_response_headers(request, denied)

    html_denied = _xfiles_html_menu_denial(request)
    if html_denied:
        return _apply_browser_response_headers(request, html_denied)

    response = await call_next(request)
    return _apply_browser_response_headers(request, response)


_TELEGRAM_SETUP_HTML_ALLOWLIST = {
    "/setup_wizard.html",
    "/tariffs.html",
}
_TELEGRAM_SETUP_REQUIRED_STATUSES = {"needs_api_credentials", "needs_auth"}
_TELEGRAM_SESSION_RECONNECTING_STATUSES = {"session_present", "unknown"}


def _is_frontend_html_shell(path: str) -> bool:
    return path == "/" or path.endswith(".html")


async def _telegram_setup_wizard_redirect_response(request: Request) -> Optional[RedirectResponse]:
    path = request.url.path or "/"
    if not _is_frontend_html_shell(path):
        return None
    if path in _TELEGRAM_SETUP_HTML_ALLOWLIST:
        return None

    try:
        runtime = await _runtime_status()
    except Exception:
        logger.exception("Telegram setup redirect check failed for %s", path)
        return None

    if runtime.auth_status == "authorized" or runtime.auth_status in _TELEGRAM_SESSION_RECONNECTING_STATUSES:
        return None
    if runtime.auth_status not in _TELEGRAM_SETUP_REQUIRED_STATUSES:
        return None

    next_url = path
    if request.url.query:
        next_url = f"{next_url}?{request.url.query}"
    query = urlencode({"next": next_url, "reason": runtime.auth_status or "not_authorized"})
    return RedirectResponse(url=f"/setup_wizard.html?{query}", status_code=307)

_RUNTIME_LOG_RETENTION_SEC = 600
_runtime_logs: deque[Dict[str, Any]] = deque()
_runtime_logs_lock = threading.Lock()
_runtime_log_counter = count(1)
_SERVER_STARTED_AT = datetime.now(timezone.utc)
_SERVER_INSTANCE_ID = uuid.uuid4().hex[:8]
_STARTUP_STATUS_LOG_LIMIT = int(os.environ.get("XFILES_STARTUP_STATUS_LOG_LIMIT", "30") or "30")
_startup_status_lock = threading.Lock()
_startup_status: Dict[str, Any] = {
    "running": True,
    "complete": False,
    "phase": "module_import",
    "progress_percent": 5.0,
    "summary": "Backend импортируется",
    "started_at": _SERVER_STARTED_AT.isoformat(),
    "updated_at": _SERVER_STARTED_AT.isoformat(),
    "last_error": None,
    "log": [
        {
            "ts": _SERVER_STARTED_AT.isoformat(),
            "phase": "module_import",
            "message": "Backend module import started",
        }
    ],
}
_lead_event_subscribers: set[asyncio.Queue] = set()
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
APP_SETTINGS_STATE_KEY = "_app_settings"
XFILES_DEALS_STATE_KEY = "_xfiles_deals"
XFILES_DEAL_AUDIT_STATE_KEY = "_xfiles_deal_audit"
XFILES_PRODUCT_MARGINS_STATE_KEY = "_xfiles_product_margins"
XFILES_CONTRACTS_STATE_KEY = "_xfiles_contracts"
XFILES_LLM_AUDIT_STATE_KEY = "_xfiles_llm_audit"
XFILES_METRIC_HISTORY_STATE_KEY = "_xfiles_metric_history"
TELEGRAM_RATE_LIMIT_STATE_KEY = "_telegram_rate_limits"
TELEGRAM_SELECTOR_CACHE_STATE_KEY = "_telegram_selector_cache"
TELEGRAM_SYNC_CONTROL_STATE_KEY = "_telegram_sync_control"
TELEGRAM_SOURCE_POLICY_STATE_KEY = "_telegram_source_policy"
SOURCE_SELECTORS_STATE_KEY = "_source_selectors"
DEFAULT_OPENROUTER_MODEL_ID = "openai/gpt-oss-120b:free"
DEFAULT_OPENROUTER_PAID_MODEL_ID = "openai/gpt-5-chat"
DEFAULT_LLM_PROVIDER = "openrouter"
DEFAULT_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
CHAT_ANALYSIS_HISTORY_STATE_KEY = "_chat_analysis_history"
CHAT_ANALYSIS_HISTORY_MAX_ITEMS = max(20, int(os.environ.get("XFILES_CHAT_ANALYSIS_HISTORY_MAX", "80") or "80"))
XFILES_LLM_AUDIT_MAX_ITEMS = max(50, int(os.environ.get("XFILES_LLM_AUDIT_MAX_ITEMS", "1000") or "1000"))
OPENROUTER_MODELS_URL = os.environ.get("PAYME_OPENROUTER_MODELS_URL", "https://openrouter.ai/api/v1/models")
OPENROUTER_CHAT_COMPLETIONS_URL = os.environ.get(
    "PAYME_OPENROUTER_CHAT_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)
OPENROUTER_REQUEST_TIMEOUT_SEC = float(os.environ.get("PAYME_OPENROUTER_TIMEOUT_SEC", "300"))
_OPENROUTER_FALLBACK_MODELS: List[Dict[str, Any]] = [
    {
        "id": DEFAULT_OPENROUTER_MODEL_ID,
        "name": "OpenAI GPT OSS 120B (free)",
        "context_length": 131072,
        "free": True,
    },
    {
        "id": "deepseek/deepseek-chat-v3-0324:free",
        "name": "DeepSeek Chat V3 0324 (free)",
        "context_length": 163840,
        "free": True,
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Meta Llama 3.3 70B Instruct (free)",
        "context_length": 131072,
        "free": True,
    },
    {
        "id": DEFAULT_OPENROUTER_PAID_MODEL_ID,
        "name": "OpenAI GPT-5 Chat (paid)",
        "context_length": 262144,
        "free": False,
    },
]
DEFAULT_OCR_SERVICE_URL = os.environ.get("PAYME_DEFAULT_OCR_SERVICE_URL", "").strip().rstrip("/")
OCR_SERVICE_URL = os.environ.get("PAYME_OCR_SERVICE_URL", DEFAULT_OCR_SERVICE_URL).strip().rstrip("/")
OCR_REQUEST_TIMEOUT_SEC = float(os.environ.get("PAYME_OCR_TIMEOUT_SEC", "600"))
OCR_HEALTH_TIMEOUT_SEC = float(os.environ.get("PAYME_OCR_HEALTH_TIMEOUT_SEC", "30"))
OCR_WARMUP_TIMEOUT_SEC = float(os.environ.get("PAYME_OCR_WARMUP_TIMEOUT_SEC", "5"))
OCR_LOCAL_FALLBACK = os.environ.get("PAYME_OCR_LOCAL_FALLBACK", "0") == "1"
MEDIA_OCR_LOOP_INTERVAL_SEC = float(os.environ.get("PAYME_MEDIA_OCR_LOOP_SEC", "10"))
_easyocr_reader = None
_easyocr_reader_lock = threading.Lock()
_image_ocr_task: Optional[asyncio.Task] = None
_media_ocr_loop_task: Optional[asyncio.Task] = None
_image_ocr_status: Dict[str, Any] = {
    "running": False,
    "processed_count": 0,
    "error_count": 0,
    "pending_count": 0,
    "crm_rows_created": 0,
    "deleted_images": 0,
    "last_media_path": None,
    "progress_current": 0,
    "progress_total": 0,
    "progress_percent": 0.0,
    "current_item": None,
    "progress_log": [],
    "last_started_at": None,
    "last_finished_at": None,
    "last_error": None,
    "available": False,
    "mode": "disabled",
}


def _normalize_ocr_service_url(value: Any) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    return f"http://{raw}"


def _default_ocr_service_url() -> str:
    return _normalize_ocr_service_url(OCR_SERVICE_URL or DEFAULT_OCR_SERVICE_URL)


def _normalize_local_web_bind(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return "localhost" if raw == "localhost" else "127.0.0.1"


def _default_local_web_port() -> int:
    raw = str(os.environ.get("HOST_WEB_PORT") or os.environ.get("WEB_PORT") or "8001").strip()
    if ":" in raw:
        raw = raw.rsplit(":", 1)[-1]
    try:
        port = int(raw)
    except (TypeError, ValueError):
        port = 8001
    return max(1, min(65535, port))


def _ocr_service_url() -> str:
    return _normalize_ocr_service_url(_get_app_settings().get("ocr_service_url") or _default_ocr_service_url())
_lead_file_summary_cache: Dict[str, Dict[str, Any]] = {}
_lead_snapshot_cache: Dict[str, Any] = {
    "items": None,
    "updated_at": 0.0,
}
_lead_snapshot_refresh_task: Optional[asyncio.Task] = None
_telegram_dialogs_cache: Dict[str, Any] = {
    "items": None,
    "updated_at": None,
    "expires_at": 0.0,
    "last_error": None,
}
_telegram_dialogs_refresh_task: Optional[asyncio.Task] = None
_TELEGRAM_DIALOGS_CACHE_TTL_SECONDS = float(os.environ.get("PAYME_DIALOGS_CACHE_TTL_SEC", "300"))
_TELEGRAM_DIALOGS_REQUEST_TIMEOUT_SEC = float(os.environ.get("PAYME_DIALOGS_REQUEST_TIMEOUT_SEC", "90"))
_ANALYSIS_AUTO_REFRESH_DEFAULT_SEC = int(os.environ.get("PAYME_ANALYSIS_AUTO_REFRESH_SEC", "300"))
_ANALYSIS_LOOP_SLEEP_SEC = float(os.environ.get("PAYME_ANALYSIS_LOOP_SLEEP_SEC", "5"))
_API_SNAPSHOT_CACHE_TTL_SEC = max(0.2, float(os.environ.get("PAYME_API_SNAPSHOT_CACHE_TTL_SEC", "1.0")))
_LEAD_SNAPSHOT_CACHE_TTL_SEC = max(1.0, float(os.environ.get("PAYME_LEAD_SNAPSHOT_CACHE_TTL_SEC", "15.0")))
_DASHBOARD_SUMMARY_CACHE_TTL_SEC = max(1.0, float(os.environ.get("PAYME_DASHBOARD_SUMMARY_CACHE_TTL_SEC", "30.0")))
_LLM_HTML_CACHE_TTL_SEC = max(1.0, float(os.environ.get("PAYME_LLM_HTML_CACHE_TTL_SEC", "15.0")))
_XFILES_DEAL_API_CACHE_TTL_SEC = max(
    1.0,
    float(os.environ.get("PAYME_XFILES_DEAL_API_CACHE_TTL_SEC", os.environ.get("XFILES_DEAL_API_CACHE_TTL_SEC", "5.0"))),
)
_STARTUP_TELEGRAM_BOOTSTRAP_ENABLED = os.environ.get("PAYME_STARTUP_TELEGRAM_BOOTSTRAP", "0") == "1"
_STARTUP_ANALYSIS_AUTOREFRESH_ENABLED = os.environ.get("PAYME_STARTUP_ANALYSIS_AUTOREFRESH", "0") == "1"
_STARTUP_DUCKDB_SYNC_ENABLED = os.environ.get("PAYME_STARTUP_DUCKDB_SYNC", "0") == "1"
_STARTUP_DUCKDB_AUTOREFRESH_ENABLED = os.environ.get("PAYME_STARTUP_DUCKDB_AUTOREFRESH", "0") == "1"
_STARTUP_OCR_SWEEP_ENABLED = os.environ.get("PAYME_STARTUP_OCR_SWEEP", "0") == "1"
_DUCKDB_REFRESH_DERIVED_ON_SYNC = os.environ.get("PAYME_DUCKDB_REFRESH_DERIVED_ON_SYNC", "0") == "1"
_api_snapshot_cache: Dict[str, Dict[str, Any]] = {}
_api_snapshot_cache_lock = threading.Lock()
_api_snapshot_async_locks: Dict[str, asyncio.Lock] = {}
_api_snapshot_async_locks_lock = threading.Lock()
_api_snapshot_refresh_tasks: Dict[str, Any] = {}
_api_snapshot_refresh_tasks_lock = threading.Lock()
_data_reset_status_lock = threading.Lock()
_data_reset_status: Dict[str, Any] = {
    "running": False,
    "progress_percent": 0.0,
    "progress_label": "Готово",
    "started_at": None,
    "updated_at": None,
    "finished_at": None,
    "last_error": None,
    "progress_log": [],
}
_XFILES_DEAL_CACHE_WARMUP_ENABLED = os.environ.get("PAYME_XFILES_DEAL_CACHE_WARMUP", "1") != "0"
_XFILES_DEAL_CACHE_PROGRESS_LOG_LIMIT = int(os.environ.get("PAYME_XFILES_DEAL_CACHE_PROGRESS_LOG_LIMIT", "20"))
_xfiles_deal_cache_warm_status_lock = threading.Lock()
_xfiles_deal_cache_warm_status: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "updated_at": None,
    "progress_current": 0,
    "progress_total": 0,
    "progress_percent": 0.0,
    "current_item": None,
    "last_error": None,
    "last_reason": None,
    "progress_log": [],
}
_postgres_schema_ready = False
_postgres_schema_lock = threading.Lock()
_postgres_last_error: Optional[str] = None
_postgres_last_error_logged_at = 0.0
_postgres_state_deals_migrated = False
_postgres_state_deals_migration_lock = threading.Lock()
_postgres_state_deals_migration_last_error: Optional[str] = None
_DUCKDB_SYNC_ENABLED = os.environ.get("PAYME_DUCKDB_ENABLED", "1") != "0"
_DUCKDB_SYNC_INTERVAL_SEC = int(os.environ.get("PAYME_DUCKDB_SYNC_INTERVAL_SEC", "300"))
_DUCKDB_LOOP_SLEEP_SEC = float(os.environ.get("PAYME_DUCKDB_LOOP_SLEEP_SEC", "5"))
_DUCKDB_PROGRESS_LOG_LIMIT = int(os.environ.get("PAYME_DUCKDB_PROGRESS_LOG_LIMIT", "50"))
_DUCKDB_BATCH_SIZE = max(500, int(os.environ.get("PAYME_DUCKDB_BATCH_SIZE", "5000")))
_DUCKDB_EXECUTEMANY_CHUNK_SIZE = max(100, int(os.environ.get("PAYME_DUCKDB_EXECUTEMANY_CHUNK_SIZE", "1000")))
_DUCKDB_PROGRESS_EMIT_SEC = max(1.0, float(os.environ.get("PAYME_DUCKDB_PROGRESS_EMIT_SEC", "3")))
_DUCKDB_LOG_EMIT_SEC = max(5.0, float(os.environ.get("PAYME_DUCKDB_LOG_EMIT_SEC", "20")))
_DUCKDB_DEFER_HEAVY_INDEXES = os.environ.get("PAYME_DUCKDB_DEFER_HEAVY_INDEXES", "1") != "0"
_DUCKDB_PARQUET_STAGING_ENABLED = os.environ.get("PAYME_DUCKDB_PARQUET_STAGING_ENABLED", "1") != "0"
_DUCKDB_PARQUET_STAGE_MIN_MB = max(1, int(os.environ.get("PAYME_DUCKDB_PARQUET_STAGE_MIN_MB", "8")))
_DUCKDB_PARQUET_STAGE_APPEND_MIN_MB = max(1, int(os.environ.get("PAYME_DUCKDB_PARQUET_STAGE_APPEND_MIN_MB", "4")))
DUCKDB_READ_PATH = Path(os.environ.get("PAYME_DUCKDB_READ_PATH", str(DUCKDB_PATH.with_name("gramlead-read.duckdb"))))
_DUCKDB_SHARED_CONNECTION_ENABLED = os.environ.get("PAYME_DUCKDB_SHARED_CONNECTION", "0") == "1"
_DUCKDB_READ_SNAPSHOT_STALE_WARN_SEC = max(
    30,
    int(os.environ.get("PAYME_DUCKDB_READ_SNAPSHOT_STALE_WARN_SEC", "180") or "180"),
)
_SYSTEM_METRICS_INTERVAL_SEC = float(os.environ.get("PAYME_SYSTEM_METRICS_INTERVAL_SEC", "5"))
_SYSTEM_METRICS_HISTORY_MAX_POINTS = int(os.environ.get("PAYME_SYSTEM_METRICS_HISTORY_MAX_POINTS", "720"))
AnalysisKind = Literal["crm", "events", "contacts"]
_ANALYSIS_KINDS: tuple[AnalysisKind, ...] = ("crm", "events", "contacts")
_analysis_refresh_tasks: Dict[str, Optional[asyncio.Task]] = {"crm": None, "events": None, "contacts": None}
_analysis_autorefresh_task: Optional[asyncio.Task] = None
_event_date_extraction_task: Optional[asyncio.Task] = None
_event_date_extraction_lock = threading.Lock()
_event_date_extraction_running = False
_event_date_extraction_runtime: Dict[str, Any] = {
    "started_at": None,
    "updated_at": None,
    "processed": 0,
    "found": 0,
    "errors": 0,
    "last_error": None,
    "rate_per_min": 0.0,
}
_routes_refresh_task: Optional[asyncio.Task] = None
_routes_refresh_lock = threading.Lock()
_ROUTES_ANALYSIS_KIND = "routes"
_ROUTES_LLM_BATCH_SIZE = max(1, int(os.environ.get("PAYME_ROUTES_LLM_BATCH_SIZE", "50")))
_duckdb_sync_task: Optional[asyncio.Task] = None
_duckdb_autorefresh_task: Optional[asyncio.Task] = None
_duckdb_live_sync_pending: bool = False
_duckdb_live_sync_timer: Optional[asyncio.TimerHandle] = None
_DUCKDB_ROW_KEY_VERSION = "v2"
_duckdb_status_lock = threading.Lock()
_duckdb_connection_lock = threading.RLock()
_duckdb_shared_connection: Any = None
_telegram_setup_error_state: Dict[str, Dict[str, Any]] = {}
_duckdb_status: Dict[str, Any] = {
    "available": duckdb is not None,
    "enabled": _DUCKDB_SYNC_ENABLED,
    "running": False,
    "cache_ready": False,
    "db_path": str(DUCKDB_PATH),
    "read_snapshot_path": str(DUCKDB_READ_PATH),
    "read_snapshot_exists": False,
    "read_snapshot_mtime": None,
    "lock_status": {},
    "source_files_total": 0,
    "source_files_indexed": 0,
    "tracked_files": 0,
    "message_rows": 0,
    "jsonl_rows_total": 0,
    "duckdb_rows_total": 0,
    "lag_rows_total": 0,
    "duplicate_message_rows": 0,
    "last_deduplicated_rows": 0,
    "file_registry_rows": 0,
    "progress_current": 0,
    "progress_total": 0,
    "progress_percent": 0.0,
    "progress_label": "Ожидание",
    "current_item": None,
    "progress_started_at": None,
    "progress_updated_at": None,
    "bytes_total": 0,
    "bytes_processed": 0,
    "rows_ingested_in_run": 0,
    "rows_per_sec": 0.0,
    "mb_per_sec": 0.0,
    "average_batch_size": 0.0,
    "current_file_rows_per_sec": 0.0,
    "current_file_mb_per_sec": 0.0,
    "sync_mode": "idle",
    "current_phase": "idle",
    "indexes_ready": False,
    "parquet_stage_enabled": _DUCKDB_PARQUET_STAGING_ENABLED,
    "parquet_stage_used": False,
    "parquet_stage_files": 0,
    "corrupt_jsonl_files": 0,
    "corrupt_jsonl_examples": [],
    "last_file_name": None,
    "last_file_duration_sec": 0.0,
    "last_file_rows": 0,
    "progress_log": [],
    "progress_history": [],
    "last_refresh_at": None,
    "last_error": None,
    "next_refresh_at": None,
    "stale_reason": "DuckDB ещё не проиндексировал сообщения",
}
_system_metrics_history: deque[Dict[str, Any]] = deque(maxlen=max(60, _SYSTEM_METRICS_HISTORY_MAX_POINTS))
_system_metrics_lock = threading.Lock()
_system_metrics_task: Optional[asyncio.Task] = None
_system_metrics_last_sample: Dict[str, float] = {"wall": time.monotonic(), "cpu": time.process_time()}
_psutil_process = psutil.Process(os.getpid()) if psutil else None
_CRM_COMMON_FIRST_NAMES = {
    "александр", "алексей", "алёна", "анастасия", "андрей", "анна", "антон", "артем", "артём",
    "богдан", "вадим", "валерий", "виктор", "виктория", "виталий", "владимир", "владислав",
    "галина", "георгий", "даниил", "денис", "дмитрий", "евгений", "екатерина", "елена",
    "игорь", "иван", "илья", "ирина", "кирилл", "ксения", "лариса", "марина", "мария",
    "максим", "михаил", "наталья", "никита", "николай", "оксана", "ольга", "павел",
    "петр", "пётр", "роман", "светлана", "сергей", "софья", "станислав", "таисия",
    "татьяна", "тимур", "фёдор", "федор", "юлия", "ян", "yaroslav", "alex", "maria",
    "ivan", "anna", "sergey", "alexey", "dmitry", "roman", "timur",
}
_CRM_SURNAME_SUFFIXES = (
    "ов", "ова", "ев", "ева", "ёв", "ёва", "ин", "ина", "ын", "ына", "ский", "ская",
    "цкий", "цкая", "енко", "ук", "юк", "ич", "вич", "дзе", "ян", "янц", "оглы",
)
_CRM_PATRONYMIC_SUFFIXES = (
    "ович", "евич", "ич", "оглы", "улы", "овна", "евна", "ична", "инична",
)
_CRM_NAME_STOPWORDS = {
    "ai", "bot", "comments", "chat", "channel", "projects", "tech", "skills",
    "группа", "канал", "комментарии", "новости", "чат", "бот", "проект", "команда",
}
_CRM_CITY_ALIASES = {
    "москва": "Москва",
    "москве": "Москва",
    "москвы": "Москва",
    "санкт-петербург": "Санкт-Петербург",
    "санкт петербург": "Санкт-Петербург",
    "петербург": "Санкт-Петербург",
    "питере": "Санкт-Петербург",
    "питер": "Санкт-Петербург",
    "казань": "Казань",
    "казани": "Казань",
    "екатеринбург": "Екатеринбург",
    "екатеринбурге": "Екатеринбург",
    "новосибирск": "Новосибирск",
    "новосибирске": "Новосибирск",
    "нижний новгород": "Нижний Новгород",
    "нижнем новгороде": "Нижний Новгород",
    "краснодар": "Краснодар",
    "краснодаре": "Краснодар",
    "самара": "Самара",
    "самаре": "Самара",
    "сочи": "Сочи",
    "сочи́": "Сочи",
    "минск": "Минск",
    "минске": "Минск",
    "алматы": "Алматы",
    "астана": "Астана",
    "тбилиси": "Тбилиси",
    "ереван": "Ереван",
    "дубай": "Дубай",
    "dubai": "Дубай",
    "london": "London",
    "berlin": "Berlin",
    "moscow": "Москва",
}
_CRM_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}\b")
_CRM_PHONE_RE = re.compile(r"(?<![\w@])(\+?\d[\d\-\(\)\s]{8,}\d)")
_CRM_TELEMOST_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?telemost\.yandex\.[a-z.]+/\S+",
    re.IGNORECASE,
)
_CRM_NAME_TOKEN_RE = re.compile(r"[A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?")
_CRM_PERSON_SEQ_RE = re.compile(
    r"\b([A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?"
    r"(?:\s+[A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?){0,2})\b"
)
_CRM_NAME_CONTEXT_PATTERNS = [
    re.compile(
        r"(?:меня\s+зовут|мое\s+имя|моё\s+имя|спикер|контакт|это)\s*[:\-]?\s*"
        r"([A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?(?:\s+[A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?){0,2})"
    ),
    re.compile(
        r"\b(?:я|i\s+am)\s+([A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?(?:\s+[A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?){0,2})"
    ),
]
_CRM_TITLE_KEYWORDS = sorted(
    {
        "account manager", "admin", "advisor", "аналитик", "архитектор", "ассистент",
        "бизнес-партнер", "бизнес-партнёр", "бухгалтер", "ceo", "cfo", "chief",
        "chief marketing officer", "chief product officer", "chief revenue officer",
        "chief technology officer", "cmo", "co-founder", "cofounder", "coo", "cpo",
        "cto", "customer success manager", "data scientist", "designer", "devops",
        "директор", "инженер", "исполнительный директор", "коммерческий директор",
        "консультант", "контент-менеджер", "копирайтер", "lead", "manager",
        "маркетолог", "менеджер", "операционный директор", "owner", "partner",
        "president", "product designer", "product manager", "project manager",
        "qa engineer", "recruiter", "researcher", "sales", "sales manager", "smm",
        "software engineer", "specialist", "team lead", "tech lead", "vp", "writer",
        "редактор", "руководитель", "сооснователь", "специалист", "тимлид", "фаундер",
        "финансовый директор", "hr", "hrd", "head", "head of", "head of sales",
        "head of marketing", "head of product", "head of customer support",
        "developer", "разработчик", "программист", "юрист",
    },
    key=len,
    reverse=True,
)
_CRM_TITLE_MODIFIERS = (
    "главный", "ведущий", "старший", "младший", "генеральный", "исполнительный",
    "технический", "финансовый", "коммерческий", "операционный", "regional",
    "senior", "junior", "lead", "chief", "deputy", "principal",
)
_crm_title_keywords_pattern = "|".join(re.escape(item) for item in _CRM_TITLE_KEYWORDS)
_crm_title_modifiers_pattern = "|".join(re.escape(item) for item in _CRM_TITLE_MODIFIERS)
_CRM_TITLE_RE = re.compile(
    rf"\b((?:(?:{_crm_title_modifiers_pattern})\s+){{0,2}}(?:{_crm_title_keywords_pattern})"
    r"(?:\s+(?:по|of)\s+[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-]+(?:\s+[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-]+){0,2})?)\b",
    re.IGNORECASE,
)
_CRM_COMPANY_PATTERNS = [
    re.compile(
        r"\b(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|ФГУП|МУП)\s+[«\"]?([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\s\-&\.]{1,60})[»\"]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\s\-&\.]{1,60})\s+(?:LLC|Inc\.?|Ltd\.?|Corp\.?|GmbH|PLC)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:компания|компании|в\s+компании|работаю\s+в|представляю|из\s+компании)\s+[«\"]?([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\s\-&\.]{1,60})[»\"]?",
        re.IGNORECASE,
    ),
]
_CRM_CITY_PATTERNS = [
    re.compile(
        r"(?:город|г\.|из|в)\s+([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё\-]+(?:\s+[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё\-]+)?)",
        re.IGNORECASE,
    ),
]
_PII_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PII_PHONE_RE = re.compile(r"(?<![\w/])(?:\+?\d[\d\s().\-]{7,}\d)(?![\w/])")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _update_data_reset_status(
    *,
    progress_percent: Optional[float] = None,
    progress_label: Optional[str] = None,
    running: Optional[bool] = None,
    last_error: Optional[str] = None,
) -> None:
    now = _utc_now().isoformat()
    with _data_reset_status_lock:
        if running is not None and running and not _data_reset_status.get("running"):
            _data_reset_status["started_at"] = now
            _data_reset_status["finished_at"] = None
            _data_reset_status["progress_log"] = []
        if running is not None:
            _data_reset_status["running"] = bool(running)
            if not running:
                _data_reset_status["finished_at"] = now
        if progress_percent is not None:
            _data_reset_status["progress_percent"] = max(0.0, min(100.0, float(progress_percent)))
        if progress_label is not None:
            _data_reset_status["progress_label"] = str(progress_label)
            _data_reset_status["progress_log"] = [
                f"{now} {progress_label}",
                *list(_data_reset_status.get("progress_log") or [])[:19],
            ]
        if last_error is not None:
            _data_reset_status["last_error"] = str(last_error) if last_error else None
        _data_reset_status["updated_at"] = now


def _build_data_reset_status() -> Dict[str, Any]:
    with _data_reset_status_lock:
        status = dict(_data_reset_status)
        status["progress_log"] = list(_data_reset_status.get("progress_log") or [])
        status["log"] = list(status["progress_log"])
        return status


def _preserve_state_for_data_reset() -> Dict[str, Any]:
    current_state = getattr(telegram_sync, "state", {}) if "telegram_sync" in globals() else {}
    return preserve_state_keys(current_state, (APP_SETTINGS_STATE_KEY, TELEGRAM_RATE_LIMIT_STATE_KEY))


def _clear_source_selectors_for_data_reset() -> None:
    _write_source_selectors([])


def _clear_payme_out_dirs_for_data_reset() -> None:
    clear_unique_directory_contents([PAYME_OUT_DIR, *LEGACY_PAYME_OUT_DIRS], ensure_path=PAYME_OUT_DIR)


def _reset_runtime_data_preserving_settings_sync() -> None:
    global _duckdb_shared_connection
    preserved_state = _preserve_state_for_data_reset()

    _update_data_reset_status(progress_percent=8, progress_label="Останавливаю подключение DuckDB")
    with _duckdb_connection_lock:
        if _duckdb_shared_connection is not None:
            try:
                _duckdb_shared_connection.close()
            except Exception:
                pass
            _duckdb_shared_connection = None

    _update_data_reset_status(progress_percent=22, progress_label="Очищаю производные кеши backend")
    with _api_snapshot_cache_lock:
        _api_snapshot_cache.clear()
    _lead_file_summary_cache.clear()
    _lead_snapshot_cache["items"] = None
    _lead_snapshot_cache["updated_at"] = 0.0
    _telegram_dialogs_cache["items"] = None
    _telegram_dialogs_cache["updated_at"] = None
    _telegram_dialogs_cache["expires_at"] = 0.0
    _telegram_dialogs_cache["last_error"] = None

    _update_data_reset_status(progress_percent=36, progress_label="Очищаю выбранные источники import, Sync и чатов")
    _clear_source_selectors_for_data_reset()
    telegram_sync.selected_chats = []
    telegram_sync.entities_by_chat_key.clear()
    telegram_sync._desired_selector_keys.clear()
    telegram_sync._enabled_chat_keys.clear()
    telegram_sync._selector_to_chat_key.clear()
    for task_map in (
        telegram_sync._chat_setup_tasks,
        telegram_sync._chat_backfill_tasks,
        telegram_sync._chat_media_backfill_tasks,
    ):
        for task in list(task_map.values()):
            try:
                task.cancel()
            except Exception:
                pass
        task_map.clear()
    try:
        telegram_sync.request_source_reload()
    except Exception:
        pass

    _update_data_reset_status(progress_percent=50, progress_label="Удаляю JSONL, HTML, media и производные файлы out/")
    _clear_payme_out_dirs_for_data_reset()

    _update_data_reset_status(progress_percent=62, progress_label="Удаляю cache/ и runtime-state, оставляю только настройки")
    if CACHE_DIR.exists():
        safe_clear_directory_contents(CACHE_DIR)

    telegram_sync.state = preserved_state
    telegram_sync.save_state()

    _update_data_reset_status(progress_percent=76, progress_label="Удаляю DuckDB-файлы, чтобы база построилась заново")
    db_parent = DUCKDB_PATH.parent
    if db_parent.exists():
        for item in db_parent.glob(f"{DUCKDB_PATH.name}*"):
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except FileNotFoundError:
                pass

    _duckdb_update_status(
        running=False,
        cache_ready=False,
        indexes_ready=False,
        source_files_total=0,
        source_files_indexed=0,
        tracked_files=0,
        message_rows=0,
        duplicate_message_rows=0,
        file_registry_rows=0,
        progress_current=0,
        progress_total=0,
        progress_percent=0.0,
        progress_label="Данные сброшены",
        current_item=None,
        bytes_total=0,
        bytes_processed=0,
        rows_ingested_in_run=0,
        sync_mode="idle",
        current_phase="idle",
        stale_reason="Данные сброшены, ожидается новая индексация",
    )
    _update_data_reset_status(progress_percent=92, progress_label="Готовлю фоновую переиндексацию DuckDB")


def _mask_pii_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""

    def _mask_phone(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10 or len(digits) > 15:
            return raw
        return "[phone masked]"

    return _PII_PHONE_RE.sub(_mask_phone, _PII_EMAIL_RE.sub("[email masked]", text))


def _runtime_log_mask_pii_enabled() -> bool:
    try:
        return bool(_get_app_settings().get("runtime_log_mask_pii", True))
    except Exception:
        return True


def _openrouter_allow_pii_enabled() -> bool:
    try:
        return bool(_get_app_settings().get("openrouter_allow_pii", False))
    except Exception:
        return False


def _prune_runtime_logs(now: Optional[datetime] = None) -> None:
    now = now or _utc_now()
    cutoff_ts = now.timestamp() - _RUNTIME_LOG_RETENTION_SEC
    while _runtime_logs:
        first = _runtime_logs[0]
        if float(first.get("ts_unix", 0)) >= cutoff_ts:
            break
        _runtime_logs.popleft()


from app.services.runtime_status import (
    _append_runtime_log,
    _background_task_statuses,
    _collect_system_metrics_snapshot,
    _dashboard_function_modes_sync,
    _dashboard_summary_payload,
    _runtime_status,
)



def _startup_status_update(
    phase: str,
    progress_percent: float,
    summary: str,
    *,
    complete: bool = False,
    last_error: Optional[str] = None,
) -> None:
    now = _utc_now().isoformat()
    safe_summary = str(summary or "").strip() or str(phase or "startup")
    safe_phase = str(phase or "startup").strip() or "startup"
    with _startup_status_lock:
        _startup_status["running"] = not complete and last_error is None
        _startup_status["complete"] = bool(complete)
        _startup_status["phase"] = safe_phase
        _startup_status["progress_percent"] = max(0.0, min(100.0, float(progress_percent or 0.0)))
        _startup_status["summary"] = safe_summary
        _startup_status["updated_at"] = now
        _startup_status["last_error"] = last_error
        log_rows = list(_startup_status.get("log") or [])
        log_rows.append({"ts": now, "phase": safe_phase, "message": safe_summary})
        _startup_status["log"] = log_rows[-_STARTUP_STATUS_LOG_LIMIT:]


def _startup_status_snapshot() -> Dict[str, Any]:
    with _startup_status_lock:
        return {
            "running": bool(_startup_status.get("running")),
            "complete": bool(_startup_status.get("complete")),
            "phase": str(_startup_status.get("phase") or ""),
            "progress_percent": float(_startup_status.get("progress_percent") or 0.0),
            "summary": str(_startup_status.get("summary") or ""),
            "started_at": _startup_status.get("started_at"),
            "updated_at": _startup_status.get("updated_at"),
            "last_error": _startup_status.get("last_error"),
            "log": list(_startup_status.get("log") or []),
        }


def _read_runtime_logs(
    minutes: int = 10,
    after_id: int = 0,
    limit: int = 0,
    channel: str = "",
) -> List[Dict[str, Any]]:
    now = _utc_now()
    normalized_channel = str(channel or "").strip().lower()
    with _runtime_logs_lock:
        _prune_runtime_logs(now)
        cutoff_ts = now.timestamp() - max(minutes, 1) * 60
        rows = [
            {
                "id": item["id"],
                "ts": item["ts"],
                "source": item["source"],
                "channel": item.get("channel") or "backend",
                "message": item["message"],
            }
            for item in _runtime_logs
            if item["id"] > after_id and float(item.get("ts_unix", 0)) >= cutoff_ts
            and (not normalized_channel or str(item.get("channel") or "backend") == normalized_channel)
        ]
    if limit > 0:
        rows = rows[-max(1, int(limit)):]
    return rows


def _api_snapshot_cache_get(cache_key: str) -> Any:
    now_mono = time.monotonic()
    with _api_snapshot_cache_lock:
        entry = _api_snapshot_cache.get(str(cache_key))
        if not entry:
            return None
        expires_at = float(entry.get("expires_at") or 0.0)
        if expires_at <= now_mono:
            _api_snapshot_cache.pop(str(cache_key), None)
            return None
        return entry.get("value")


def _api_snapshot_cache_set(cache_key: str, value: Any, ttl_sec: float = _API_SNAPSHOT_CACHE_TTL_SEC) -> Any:
    safe_ttl = max(0.05, float(ttl_sec or _API_SNAPSHOT_CACHE_TTL_SEC))
    with _api_snapshot_cache_lock:
        _api_snapshot_cache[str(cache_key)] = {
            "value": value,
            "created_at": time.monotonic(),
            "expires_at": time.monotonic() + safe_ttl,
        }
    return value


def _api_snapshot_cache_peek(cache_key: str) -> Optional[Dict[str, Any]]:
    now_mono = time.monotonic()
    with _api_snapshot_cache_lock:
        entry = _api_snapshot_cache.get(str(cache_key))
        if not entry:
            return None
        return {
            "value": entry.get("value"),
            "created_at": float(entry.get("created_at") or 0.0),
            "expires_at": float(entry.get("expires_at") or 0.0),
            "fresh": float(entry.get("expires_at") or 0.0) > now_mono,
        }


def _api_snapshot_cache_clear_prefix(prefix: str) -> None:
    normalized = str(prefix)
    with _api_snapshot_cache_lock:
        for cache_key in list(_api_snapshot_cache.keys()):
            if str(cache_key).startswith(normalized):
                _api_snapshot_cache.pop(cache_key, None)


def _cached_sync_snapshot(cache_key: str, factory, ttl_sec: float = _API_SNAPSHOT_CACHE_TTL_SEC) -> Any:
    cached = _api_snapshot_cache_get(cache_key)
    if cached is not None:
        return cached
    value = factory()
    return _api_snapshot_cache_set(cache_key, value, ttl_sec=ttl_sec)


def _snapshot_refresh_handle_alive(handle: Any) -> bool:
    if handle is None:
        return False
    done = getattr(handle, "done", None)
    if callable(done):
        try:
            return not bool(done())
        except Exception:
            return False
    is_alive = getattr(handle, "is_alive", None)
    if callable(is_alive):
        try:
            return bool(is_alive())
        except Exception:
            return False
    return False


def _snapshot_refresh_worker(cache_key: str, factory, ttl_sec: float) -> None:
    try:
        value = factory()
        _api_snapshot_cache_set(cache_key, value, ttl_sec=ttl_sec)
    except Exception as exc:
        _append_runtime_log("cache", f"snapshot refresh failed for {cache_key}: {exc}")
    finally:
        with _api_snapshot_refresh_tasks_lock:
            _api_snapshot_refresh_tasks.pop(str(cache_key), None)


def _schedule_snapshot_refresh(cache_key: str, factory, ttl_sec: float = _API_SNAPSHOT_CACHE_TTL_SEC) -> bool:
    normalized_key = str(cache_key)
    with _api_snapshot_refresh_tasks_lock:
        existing = _api_snapshot_refresh_tasks.get(normalized_key)
        if _snapshot_refresh_handle_alive(existing):
            return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        thread = threading.Thread(
            target=_snapshot_refresh_worker,
            args=(normalized_key, factory, ttl_sec),
            name=f"snapshot-refresh-{normalized_key[:32]}",
            daemon=True,
        )
        with _api_snapshot_refresh_tasks_lock:
            _api_snapshot_refresh_tasks[normalized_key] = thread
        thread.start()
        return True
    task = loop.create_task(asyncio.to_thread(_snapshot_refresh_worker, normalized_key, factory, ttl_sec))
    with _api_snapshot_refresh_tasks_lock:
        _api_snapshot_refresh_tasks[normalized_key] = task
    return True


async def _async_snapshot_refresh_worker(cache_key: str, factory, ttl_sec: float) -> None:
    try:
        value = await factory()
        _api_snapshot_cache_set(cache_key, value, ttl_sec=ttl_sec)
    except Exception as exc:
        _append_runtime_log("cache", f"async snapshot refresh failed for {cache_key}: {exc}")
    finally:
        with _api_snapshot_refresh_tasks_lock:
            _api_snapshot_refresh_tasks.pop(str(cache_key), None)


def _schedule_async_snapshot_refresh(cache_key: str, factory, ttl_sec: float = _API_SNAPSHOT_CACHE_TTL_SEC) -> bool:
    normalized_key = str(cache_key)
    with _api_snapshot_refresh_tasks_lock:
        existing = _api_snapshot_refresh_tasks.get(normalized_key)
        if _snapshot_refresh_handle_alive(existing):
            return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        thread = threading.Thread(
            target=lambda: asyncio.run(_async_snapshot_refresh_worker(normalized_key, factory, ttl_sec)),
            name=f"async-snapshot-refresh-{normalized_key[:32]}",
            daemon=True,
        )
        with _api_snapshot_refresh_tasks_lock:
            _api_snapshot_refresh_tasks[normalized_key] = thread
        thread.start()
        return True
    task = loop.create_task(_async_snapshot_refresh_worker(normalized_key, factory, ttl_sec))
    with _api_snapshot_refresh_tasks_lock:
        _api_snapshot_refresh_tasks[normalized_key] = task
    return True


def _cached_sync_snapshot_fast(
    cache_key: str,
    factory,
    ttl_sec: float = _API_SNAPSHOT_CACHE_TTL_SEC,
    stale_ttl_sec: float = 300.0,
) -> Any:
    cached = _api_snapshot_cache_peek(cache_key)
    if cached and cached.get("fresh"):
        return cached.get("value")
    if cached is not None:
        created_at = float(cached.get("created_at") or 0.0)
        stale_deadline = created_at + max(0.0, float(ttl_sec or 0.0)) + max(0.0, float(stale_ttl_sec or 0.0))
        if not created_at or stale_deadline >= time.monotonic():
            _schedule_snapshot_refresh(cache_key, factory, ttl_sec=ttl_sec)
            return cached.get("value")
    value = factory()
    return _api_snapshot_cache_set(cache_key, value, ttl_sec=ttl_sec)


def _api_snapshot_async_lock(cache_key: str) -> asyncio.Lock:
    normalized_key = str(cache_key)
    with _api_snapshot_async_locks_lock:
        lock = _api_snapshot_async_locks.get(normalized_key)
        if lock is None:
            lock = asyncio.Lock()
            _api_snapshot_async_locks[normalized_key] = lock
        return lock


async def _cached_async_snapshot(
    cache_key: str,
    factory,
    ttl_sec: float = _API_SNAPSHOT_CACHE_TTL_SEC,
    stale_ttl_sec: float = 0.0,
) -> Any:
    cached_entry = _api_snapshot_cache_peek(cache_key)
    if cached_entry and cached_entry.get("fresh"):
        return cached_entry.get("value")
    if cached_entry is not None and float(stale_ttl_sec or 0.0) > 0.0:
        created_at = float(cached_entry.get("created_at") or 0.0)
        stale_deadline = created_at + max(0.0, float(ttl_sec or 0.0)) + max(0.0, float(stale_ttl_sec or 0.0))
        if created_at and stale_deadline >= time.monotonic():
            _schedule_async_snapshot_refresh(cache_key, factory, ttl_sec=ttl_sec)
            return cached_entry.get("value")
    lock = _api_snapshot_async_lock(cache_key)
    async with lock:
        cached_entry = _api_snapshot_cache_peek(cache_key)
        if cached_entry and cached_entry.get("fresh"):
            return cached_entry.get("value")
        if cached_entry is not None and float(stale_ttl_sec or 0.0) > 0.0:
            created_at = float(cached_entry.get("created_at") or 0.0)
            stale_deadline = created_at + max(0.0, float(ttl_sec or 0.0)) + max(0.0, float(stale_ttl_sec or 0.0))
            if created_at and stale_deadline >= time.monotonic():
                _schedule_async_snapshot_refresh(cache_key, factory, ttl_sec=ttl_sec)
                return cached_entry.get("value")
        value = await factory()
        return _api_snapshot_cache_set(cache_key, value, ttl_sec=ttl_sec)


def _dashboard_preview_model_list(items: List[Any], limit: int = 10) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in (items or [])[: max(1, int(limit))]:
        if isinstance(item, BaseModel):
            result.append(item.model_dump())
        elif isinstance(item, dict):
            result.append(dict(item))
    return result


def _duckdb_count_value_sync(sql: str, params: Optional[List[Any]] = None) -> int:
    if duckdb is None or not DUCKDB_PATH.exists():
        return 0
    conn = _duckdb_connect_readonly()
    try:
        row = conn.execute(sql, params or []).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


def _duckdb_dashboard_counts_sync() -> Dict[str, int]:
    counts = {
        "leads": 0,
        "contacts": 0,
        "crm": 0,
        "events": 0,
    }
    if not _duckdb_contacts_ready():
        return counts

    contact_key_sql = _duckdb_contact_key_sql()
    counts["leads"] = max(
        _duckdb_count_value_sync("SELECT COUNT(DISTINCT source_jsonl) FROM messages_raw"),
        _duckdb_count_value_sync("SELECT COUNT(*) FROM file_registry"),
    )
    counts["contacts"] = _duckdb_count_value_sync(
        f"""
        SELECT COUNT(DISTINCT {contact_key_sql})
        FROM messages_raw
        WHERE {contact_key_sql} IS NOT NULL
        """
    )
    counts["crm"] = _duckdb_count_value_sync("SELECT COUNT(*) FROM crm_contacts")
    counts["events"] = _duckdb_count_value_sync(
        "SELECT COUNT(*) FROM event_messages WHERE keyword_hash = ?",
        [_keywords_hash(_get_event_keywords())],
    )
    return counts


def _status_attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _dashboard_mode_row(
    key: str,
    title: str,
    mode: str,
    source: str,
    tone: str,
    status: str,
    next_action: str,
) -> Dict[str, str]:
    return {
        "key": key,
        "title": title,
        "mode": mode,
        "source": source,
        "tone": tone if tone in {"green", "yellow", "red"} else "yellow",
        "status": status,
        "next_action": next_action,
    }


def _analysis_mode_row(key: str, title: str, status: Any, source: str) -> Dict[str, str]:
    running = bool(_status_attr(status, "running", False))
    last_error = str(_status_attr(status, "last_error", "") or "")
    total_rows = int(_status_attr(status, "total_rows", 0) or 0)
    cache_ready = bool(_status_attr(status, "cache_ready", False))
    next_auto = _status_attr(status, "next_auto_refresh_at", None)
    last_refresh = _status_attr(status, "last_refresh_at", None)
    if last_error:
        tone = "red"
        text = last_error[:180]
    elif running:
        tone = "yellow"
        text = f"Фоновая обработка · строк {total_rows}"
    elif cache_ready or total_rows > 0:
        tone = "green"
        text = f"Локальный кеш готов · строк {total_rows}"
    else:
        tone = "yellow"
        text = "Кеш ещё пустой"
    next_action = f"Следующее автообновление: {next_auto}" if next_auto else "Открывается из локального кеша"
    if last_refresh and not next_auto:
        next_action = f"Последнее обновление: {last_refresh}"
    return _dashboard_mode_row(key, title, "local-cache", source, tone, text, next_action)






def _detect_server_mode() -> Literal["docker", "local"]:
    if Path("/.dockerenv").exists():
        return "docker"
    if os.environ.get("PAYME_RUNNING_IN_DOCKER") == "1":
        return "docker"
    return "local"


def _duckdb_sql_string_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _server_runtime_snapshot() -> Dict[str, Any]:
    now = _utc_now()
    uptime_sec = max(0, int((now - _SERVER_STARTED_AT).total_seconds()))
    startup = _startup_status_snapshot()
    return {
        "instance_id": _SERVER_INSTANCE_ID,
        "started_at": _SERVER_STARTED_AT.isoformat(),
        "uptime_sec": uptime_sec,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "mode": _detect_server_mode(),
        "startup": startup,
        "startup_running": bool(startup.get("running")),
        "startup_progress_percent": float(startup.get("progress_percent") or 0.0),
        "startup_phase": str(startup.get("phase") or ""),
        "startup_summary": str(startup.get("summary") or ""),
    }


def _round_metric(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value or 0.0), digits)
    except Exception:
        return 0.0


def _fallback_memory_snapshot() -> tuple[float, float, float]:
    total_bytes = 0.0
    available_bytes = 0.0
    try:
        page_size = float(os.sysconf("SC_PAGE_SIZE"))
        phys_pages = float(os.sysconf("SC_PHYS_PAGES"))
        total_bytes = page_size * phys_pages
        try:
            available_bytes = page_size * float(os.sysconf("SC_AVPHYS_PAGES"))
        except Exception:
            available_bytes = 0.0
    except Exception:
        total_bytes = 0.0
        available_bytes = 0.0
    used_bytes = max(0.0, total_bytes - available_bytes) if total_bytes > 0 else 0.0
    percent = (used_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0
    return used_bytes / (1024 * 1024), total_bytes / (1024 * 1024), percent


def _process_memory_mb_fallback() -> float:
    try:
        rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            return rss / (1024 * 1024)
        return rss / 1024
    except Exception:
        return 0.0


def _process_cpu_percent_fallback() -> float:
    now_wall = time.monotonic()
    now_cpu = time.process_time()
    cpu_count = max(1, int(os.cpu_count() or 1))
    with _system_metrics_lock:
        prev_wall = float(_system_metrics_last_sample.get("wall") or now_wall)
        prev_cpu = float(_system_metrics_last_sample.get("cpu") or now_cpu)
        _system_metrics_last_sample["wall"] = now_wall
        _system_metrics_last_sample["cpu"] = now_cpu
    wall_delta = max(0.001, now_wall - prev_wall)
    cpu_delta = max(0.0, now_cpu - prev_cpu)
    return max(0.0, min(100.0, (cpu_delta / wall_delta) * 100.0 / cpu_count))


def _safe_open_files_count() -> int:
    if _psutil_process is not None:
        try:
            return len(_psutil_process.open_files())
        except Exception:
            pass
    for probe in ("/proc/self/fd", "/dev/fd"):
        try:
            return len(os.listdir(probe))
        except Exception:
            continue
    return 0


def _safe_thread_count() -> int:
    if _psutil_process is not None:
        try:
            return int(_psutil_process.num_threads())
        except Exception:
            pass
    return threading.active_count()




def _record_system_metrics_snapshot() -> Dict[str, Any]:
    snapshot = _collect_system_metrics_snapshot()
    point = {
        "ts": snapshot["ts"],
        "cpu_percent": snapshot["cpu_percent"],
        "memory_percent": snapshot["memory_percent"],
        "process_cpu_percent": snapshot["process_cpu_percent"],
        "process_memory_mb": snapshot["process_memory_mb"],
    }
    with _system_metrics_lock:
        _system_metrics_history.append(point)
    return snapshot


def _latest_system_metrics_snapshot() -> Dict[str, Any]:
    snapshot = _collect_system_metrics_snapshot()
    with _system_metrics_lock:
        if _system_metrics_history:
            latest = dict(_system_metrics_history[-1])
            snapshot.update({
                "ts": latest.get("ts") or snapshot["ts"],
                "cpu_percent": latest.get("cpu_percent", snapshot["cpu_percent"]),
                "memory_percent": latest.get("memory_percent", snapshot["memory_percent"]),
                "process_cpu_percent": latest.get("process_cpu_percent", snapshot["process_cpu_percent"]),
                "process_memory_mb": latest.get("process_memory_mb", snapshot["process_memory_mb"]),
            })
    return snapshot


def _system_metrics_history_points(limit: int = 60) -> List[Dict[str, Any]]:
    with _system_metrics_lock:
        rows = list(_system_metrics_history)[-max(1, int(limit)):]
    return [dict(item) for item in rows]


def _system_metrics_payload(history_points: int = 60) -> Dict[str, Any]:
    snapshot = _latest_system_metrics_snapshot()
    history = [SystemMetricPointDTO(**row).model_dump() for row in _system_metrics_history_points(limit=history_points)]
    tasks = [item.model_dump() for item in _background_task_statuses()]
    return {
        **snapshot,
        "history": history,
        "tasks": tasks,
    }


def _duckdb_source_files() -> List[Path]:
    return sorted(PAYME_OUT_DIR.glob("*.jsonl"))


def _duckdb_status_snapshot() -> Dict[str, Any]:
    with _duckdb_status_lock:
        return dict(_duckdb_status)


def _duckdb_append_log(message: str) -> None:
    now = _utc_now()
    line = f"{now.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    with _duckdb_status_lock:
        rows = list(_duckdb_status.get("progress_log") or [])
        rows.append(line)
        _duckdb_status["progress_log"] = rows[-max(10, _DUCKDB_PROGRESS_LOG_LIMIT) :]
        if _duckdb_status.get("running"):
            _duckdb_status["progress_updated_at"] = now.isoformat()


def _duckdb_append_progress_snapshot() -> None:
    with _duckdb_status_lock:
        line = (
            f"{_utc_now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"{round(float(_duckdb_status.get('progress_percent') or 0.0), 2)}% "
            f"({_duckdb_status.get('progress_current') or 0}/{_duckdb_status.get('progress_total') or 0}) "
            f"{str(_duckdb_status.get('current_item') or _duckdb_status.get('progress_label') or '').strip()}"
        ).strip()
        rows = list(_duckdb_status.get("progress_history") or [])
        if rows and rows[-1] == line:
            return
        rows.append(line)
        _duckdb_status["progress_history"] = rows[-max(10, _DUCKDB_PROGRESS_LOG_LIMIT) :]


def _duckdb_update_status(**kwargs: Any) -> None:
    should_capture_progress = any(key in kwargs for key in ("progress_current", "progress_total", "progress_percent", "current_item", "progress_label"))
    with _duckdb_status_lock:
        if should_capture_progress:
            kwargs = {**kwargs, "progress_updated_at": _utc_now().isoformat()}
        _duckdb_status.update(kwargs)
    if should_capture_progress:
        _duckdb_append_progress_snapshot()


def _duckdb_lock_status_snapshot() -> Dict[str, Any]:
    acquired = False
    try:
        acquired = _duckdb_connection_lock.acquire(blocking=False)
        internal_lock_held = not acquired
    except Exception:
        internal_lock_held = False
    finally:
        if acquired:
            try:
                _duckdb_connection_lock.release()
            except Exception:
                pass
    snapshot_exists = DUCKDB_READ_PATH.exists()
    snapshot_age_sec: Optional[float] = None
    snapshot_mtime: Optional[str] = None
    if snapshot_exists:
        try:
            stat = DUCKDB_READ_PATH.stat()
            snapshot_age_sec = max(0.0, time.time() - float(stat.st_mtime))
            snapshot_mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        except Exception:
            snapshot_age_sec = None
            snapshot_mtime = None
    snapshot_stale = bool(snapshot_age_sec is None or snapshot_age_sec > _DUCKDB_READ_SNAPSHOT_STALE_WARN_SEC)
    warning = None
    if not snapshot_exists:
        warning = "DuckDB read snapshot is missing; external readers should wait for gramlead-read.duckdb."
    elif snapshot_stale:
        warning = (
            "DuckDB read snapshot is stale: "
            f"{int(snapshot_age_sec or 0)}s old, threshold {_DUCKDB_READ_SNAPSHOT_STALE_WARN_SEC}s."
        )
    return {
        "internal_lock_held": internal_lock_held,
        "shared_connection_open": _duckdb_shared_connection is not None,
        "writer_path": str(DUCKDB_PATH),
        "read_snapshot_path": str(DUCKDB_READ_PATH),
        "read_snapshot_exists": DUCKDB_READ_PATH.exists(),
        "read_snapshot_mtime": snapshot_mtime,
        "read_snapshot_age_sec": snapshot_age_sec,
        "read_snapshot_stale": snapshot_stale,
        "read_snapshot_stale_threshold_sec": _DUCKDB_READ_SNAPSHOT_STALE_WARN_SEC,
        "recommended_read_path": str(DUCKDB_READ_PATH if snapshot_exists else DUCKDB_PATH),
        "warning": warning,
    }


def _duckdb_bootstrap_status_from_existing_db() -> Dict[str, Any]:
    counts = _duckdb_counts_sync()
    source_files_total = len(_duckdb_source_files())
    cache_ready = counts["message_rows"] > 0 or counts["tracked_files"] > 0
    corrupt_jsonl = _duckdb_corrupt_jsonl_snapshot()
    _duckdb_update_status(
        available=bool(duckdb is not None),
        enabled=bool(_DUCKDB_SYNC_ENABLED),
        db_path=str(DUCKDB_PATH),
        cache_ready=cache_ready,
        indexes_ready=cache_ready,
        source_files_total=source_files_total,
        source_files_indexed=counts["source_files_indexed"],
        tracked_files=counts["tracked_files"],
        file_registry_rows=counts["file_registry_rows"],
        message_rows=counts["message_rows"],
        jsonl_rows_total=counts.get("jsonl_rows_total", 0),
        duckdb_rows_total=counts.get("duckdb_rows_total", counts["message_rows"]),
        lag_rows_total=counts.get("lag_rows_total", 0),
        duplicate_message_rows=counts["duplicate_message_rows"],
        progress_current=counts["source_files_indexed"] if cache_ready else 0,
        progress_total=source_files_total if source_files_total > 0 else counts["tracked_files"],
        progress_percent=(
            round((counts["source_files_indexed"] / float(source_files_total)) * 100.0, 2)
            if source_files_total > 0 else 0.0
        ),
        progress_label="DuckDB готов" if cache_ready else "Ожидание",
        current_item=None,
        corrupt_jsonl_files=int(corrupt_jsonl.get("count") or 0),
        corrupt_jsonl_examples=list(corrupt_jsonl.get("examples") or []),
        last_error=None,
        stale_reason=None if cache_ready else "DuckDB ещё не проиндексировал сообщения",
    )
    return _duckdb_status_snapshot()


def _telegram_setup_error_backoff_seconds(exc: Exception) -> int:
    text = str(exc or "").lower()
    if "could not find the input entity for peeruser" in text:
        return 600
    if "database is locked" in text:
        return 120
    return 60


def _should_emit_telegram_setup_error(chat_selector: Union[str, int], exc: Exception) -> bool:
    selector_key = str(chat_selector)
    error_text = f"{type(exc).__name__}:{exc}"
    now_mono = time.monotonic()
    state = _telegram_setup_error_state.get(selector_key) or {}
    next_allowed_at = float(state.get("next_allowed_at") or 0.0)
    if state.get("error_text") == error_text and now_mono < next_allowed_at:
        return False
    cooldown_sec = _telegram_setup_error_backoff_seconds(exc)
    _telegram_setup_error_state[selector_key] = {
        "error_text": error_text,
        "next_allowed_at": now_mono + cooldown_sec,
    }
    return True


def _schedule_duckdb_dependent_refreshes(force_full: bool = False) -> List[str]:
    scheduled: List[str] = []
    # Contacts are cheap enough to refresh after DB sync. CRM/events are heavy
    # derived layers, so by default they refresh only from their own UI/config.
    ordered_kinds: List[AnalysisKind] = ["contacts"]
    if _DUCKDB_REFRESH_DERIVED_ON_SYNC:
        ordered_kinds.extend(["crm", "events"])
    for kind in ordered_kinds:
        state = _analysis_state(kind)
        if kind != "contacts" and not bool(state.get("enabled", True)):
            continue
        if _schedule_analysis_refresh(kind, force_full=force_full):
            scheduled.append(kind)
    return scheduled


def _reset_stale_analysis_running_flags() -> None:
    changed = False
    for kind in _ANALYSIS_KINDS:
        state = _analysis_state(kind)
        task = _analysis_refresh_tasks.get(kind)
        if not bool(state.get("running")):
            continue
        if task is not None and not task.done():
            continue
        state["running"] = False
        state["current_item"] = None
        if not state.get("last_error"):
            state["progress_label"] = "Ожидание" if int(state.get("total_rows") or 0) <= 0 else "Готово"
        _analysis_progress_log(kind, "Сброшен зависший running после перезапуска Docker")
        changed = True
    if changed:
        telegram_sync.save_state()


def _duckdb_next_refresh_at(last_refresh_at: Optional[str]) -> Optional[str]:
    if not last_refresh_at:
        return None
    try:
        last_dt = datetime.fromisoformat(str(last_refresh_at))
    except Exception:
        return None
    return (last_dt + timedelta(seconds=max(15, _DUCKDB_SYNC_INTERVAL_SEC))).isoformat()


def _duckdb_counts_sync() -> Dict[str, int]:
    if duckdb is None or not DUCKDB_PATH.exists():
        return {
            "tracked_files": 0,
            "message_rows": 0,
            "duplicate_message_rows": 0,
            "file_registry_rows": 0,
            "source_files_indexed": 0,
            "jsonl_rows_total": 0,
            "duckdb_rows_total": 0,
            "lag_rows_total": 0,
        }
    conn = _duckdb_connect_readonly()
    try:
        tracked_files = int(conn.execute("SELECT COUNT(*) FROM file_registry").fetchone()[0] or 0)
        message_rows = int(conn.execute("SELECT COUNT(*) FROM messages_raw").fetchone()[0] or 0)
        duplicate_message_rows = _duckdb_duplicate_message_rows_count_sync(conn)
        source_files_indexed = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM file_registry
                WHERE ingested_offset >= size_bytes
                """
            ).fetchone()[0]
            or 0
        )
        try:
            totals_row = conn.execute(
                """
                SELECT
                    coalesce(sum(records_count_jsonl), 0),
                    coalesce(sum(records_count_duckdb), 0),
                    coalesce(sum(lag_rows), 0)
                FROM file_registry
                """
            ).fetchone()
            jsonl_rows_total = int((totals_row[0] if totals_row else 0) or 0)
            duckdb_rows_total = int((totals_row[1] if totals_row else 0) or 0)
            lag_rows_total = int((totals_row[2] if totals_row else 0) or 0)
        except Exception:
            jsonl_rows_total = 0
            duckdb_rows_total = message_rows
            lag_rows_total = 0
        return {
            "tracked_files": tracked_files,
            "message_rows": message_rows,
            "duplicate_message_rows": duplicate_message_rows,
            "file_registry_rows": tracked_files,
            "source_files_indexed": source_files_indexed,
            "jsonl_rows_total": jsonl_rows_total,
            "duckdb_rows_total": duckdb_rows_total,
            "lag_rows_total": lag_rows_total,
        }
    except Exception:
        return {
            "tracked_files": 0,
            "message_rows": 0,
            "duplicate_message_rows": 0,
            "file_registry_rows": 0,
            "source_files_indexed": 0,
            "jsonl_rows_total": 0,
            "duckdb_rows_total": 0,
            "lag_rows_total": 0,
        }
    finally:
        conn.close()


def _build_duckdb_status() -> "DuckDbStatusDTO":
    snapshot = _duckdb_status_snapshot()
    if (
        duckdb is not None
        and DUCKDB_PATH.exists()
        and not snapshot.get("running")
        and (
            int(snapshot.get("tracked_files") or 0) <= 0
            or int(snapshot.get("message_rows") or 0) <= 0
            or int(snapshot.get("source_files_indexed") or 0) <= 0
        )
    ):
        snapshot = _duckdb_bootstrap_status_from_existing_db()
    snapshot["available"] = bool(duckdb is not None)
    snapshot["enabled"] = bool(_DUCKDB_SYNC_ENABLED)
    snapshot["db_path"] = str(DUCKDB_PATH)
    snapshot["read_snapshot_path"] = str(DUCKDB_READ_PATH)
    snapshot["read_snapshot_exists"] = DUCKDB_READ_PATH.exists()
    snapshot["read_snapshot_mtime"] = (
        datetime.fromtimestamp(DUCKDB_READ_PATH.stat().st_mtime, timezone.utc).isoformat()
        if DUCKDB_READ_PATH.exists()
        else None
    )
    snapshot["lock_status"] = _duckdb_lock_status_snapshot()
    source_files_total = len(_duckdb_source_files())
    snapshot["source_files_total"] = source_files_total
    snapshot["files_on_disk"] = source_files_total
    snapshot["files_indexed"] = int(snapshot.get("source_files_indexed") or 0)
    snapshot["files_with_rows"] = int(snapshot.get("source_files_indexed") or 0)
    snapshot["next_refresh_at"] = _duckdb_next_refresh_at(snapshot.get("last_refresh_at"))
    return DuckDbStatusDTO(**snapshot)


def _ensure_duckdb_dir_exists() -> None:
    DUCKDB_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_parquet_dir_exists() -> None:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_legacy_cache_archive_dir_exists() -> None:
    LEGACY_CACHE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def _duckdb_connect():
    global _duckdb_shared_connection
    if duckdb is None:
        raise RuntimeError("duckdb dependency is not installed")
    _ensure_duckdb_dir_exists()
    _duckdb_connection_lock.acquire()
    try:
        if not _DUCKDB_SHARED_CONNECTION_ENABLED:
            conn = duckdb.connect(str(DUCKDB_PATH))
        elif _duckdb_shared_connection is None:
            _duckdb_shared_connection = duckdb.connect(str(DUCKDB_PATH))
            conn = _duckdb_shared_connection
        else:
            conn = _duckdb_shared_connection
    except Exception:
        _duckdb_connection_lock.release()
        raise

    class _DuckDbLockedConnection:
        def __init__(self, inner: Any):
            self._inner = inner
            self._closed = False

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            try:
                if not _DUCKDB_SHARED_CONNECTION_ENABLED:
                    self._inner.close()
            finally:
                _duckdb_connection_lock.release()

    return _DuckDbLockedConnection(conn)


def _duckdb_read_path(prefer_snapshot: bool = True) -> Path:
    if prefer_snapshot and DUCKDB_READ_PATH.exists():
        return DUCKDB_READ_PATH
    return DUCKDB_PATH


def _duckdb_connect_readonly(prefer_snapshot: bool = True):
    if duckdb is None:
        raise RuntimeError("duckdb dependency is not installed")
    path = _duckdb_read_path(prefer_snapshot=prefer_snapshot)
    if not path.exists():
        raise FileNotFoundError(f"DuckDB read database not found: {path}")
    return duckdb.connect(str(path), read_only=True)


from app.storage.duckdb_store import (
    _duckdb_export_parquet_sync,
    _duckdb_ingest_sync,
    _duckdb_init_schema_sync,
    _duckdb_load_contact_message_rows,
    _duckdb_load_contact_rows,
    _duckdb_load_crm_rows,
    _duckdb_load_event_rows,
    _duckdb_load_lead_messages,
    _duckdb_load_lead_registry_rows,
    _duckdb_load_lead_rows,
    _duckdb_rebuild_event_messages_sync,
    _duckdb_search_messages_page,
    _duckdb_search_sql_filters,
    _duckdb_stage_jsonl_to_parquet_sync,
)
from app.storage.duckdb.maintenance import ensure_indexes as _ensure_duckdb_indexes



def _legacy_cache_cleanup_targets() -> List[Path]:
    return [
        CACHE_DIR / "contacts_cache.json",
        CACHE_DIR / "contacts_messages.jsonl",
        CACHE_DIR / "crm_cache.json",
        CACHE_DIR / "events_cache.json",
    ]


def _archive_legacy_cache_files_sync() -> Dict[str, Any]:
    _ensure_legacy_cache_archive_dir_exists()
    stamp = _utc_now().strftime("%Y%m%d-%H%M%S")
    archive_dir = (LEGACY_CACHE_ARCHIVE_DIR / stamp).resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_files: List[str] = []
    skipped_files: List[str] = []
    manifest: List[Dict[str, Any]] = []

    for source in _legacy_cache_cleanup_targets():
        if not source.exists():
            skipped_files.append(_path_to_app_relative(source))
            continue
        target = archive_dir / source.name
        if target.exists():
            target = archive_dir / f"{source.stem}-{uuid.uuid4().hex[:8]}{source.suffix}"
        stat = source.stat()
        shutil.move(str(source), str(target))
        archived_files.append(_path_to_app_relative(target))
        manifest.append(
            {
                "source": _path_to_app_relative(source),
                "archived_to": _path_to_app_relative(target),
                "size_bytes": int(stat.st_size),
                "archived_at": _utc_now().isoformat(),
            }
        )

    manifest_path = archive_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "archive_dir": _path_to_app_relative(archive_dir),
        "archived_files": archived_files,
        "skipped_files": skipped_files,
    }




def _duckdb_ensure_indexes_sync(include_heavy: bool = True) -> None:
    conn = _duckdb_connect()
    try:
        _ensure_duckdb_indexes(conn, include_heavy=include_heavy)
    finally:
        conn.close()


def _duckdb_stage_min_bytes() -> int:
    return max(1, _DUCKDB_PARQUET_STAGE_MIN_MB) * 1024 * 1024


def _duckdb_stage_append_min_bytes() -> int:
    return max(1, _DUCKDB_PARQUET_STAGE_APPEND_MIN_MB) * 1024 * 1024


def _duckdb_file_has_parquet_magic(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(4) == b"PAR1"
    except OSError:
        return False


def _duckdb_file_looks_like_parquet(path: Path) -> bool:
    return path.suffix.lower() == ".parquet" and _duckdb_file_has_parquet_magic(path)


def _duckdb_jsonl_has_parquet_payload(path: Path) -> bool:
    return path.suffix.lower() == ".jsonl" and _duckdb_file_has_parquet_magic(path)


def _duckdb_corrupt_jsonl_snapshot(limit: int = 5) -> Dict[str, Any]:
    examples: List[str] = []
    total = 0
    for path in _duckdb_source_files():
        if not _duckdb_jsonl_has_parquet_payload(path):
            continue
        total += 1
        if len(examples) < max(1, int(limit or 5)):
            examples.append(path.name)
    return {"count": total, "examples": examples}


def _duckdb_stage_parquet_path(path: Path, stat: os.stat_result) -> Path:
    _ensure_parquet_dir_exists()
    source_rel = _path_to_app_relative(path)
    source_key = hashlib.sha1(source_rel.encode("utf-8", errors="ignore")).hexdigest()[:12]
    version = f"{_DUCKDB_ROW_KEY_VERSION}-{int(stat.st_mtime)}-{int(stat.st_size)}"
    return (PARQUET_DIR / f"{path.stem}-{source_key}-{version}.parquet").resolve()


def _duckdb_should_use_parquet_stage(
    path: Path,
    stat: os.stat_result,
    bootstrap_mode: bool,
    prev_offset: int = 0,
    reset_file: bool = False,
) -> bool:
    if _duckdb_file_looks_like_parquet(path):
        return True
    if not _DUCKDB_PARQUET_STAGING_ENABLED or path.suffix.lower() != ".jsonl":
        return False
    file_size = int(stat.st_size or 0)
    if bootstrap_mode or reset_file:
        return file_size >= _duckdb_stage_min_bytes()
    append_bytes = max(0, file_size - max(0, int(prev_offset or 0)))
    return append_bytes >= _duckdb_stage_append_min_bytes()


def _duckdb_cleanup_stage_sidecars_sync(path: Path, keep_path: Optional[Path] = None) -> None:
    if not PARQUET_DIR.exists():
        return
    prefix = f"{path.stem}-"
    keep_resolved = keep_path.resolve() if keep_path else None
    for candidate in PARQUET_DIR.glob(f"{prefix}*.parquet"):
        try:
            resolved = candidate.resolve()
            if keep_resolved and resolved == keep_resolved:
                continue
            candidate.unlink(missing_ok=True)
        except OSError:
            continue


def _duckdb_stage_parquet_is_valid_sync(path: Path) -> bool:
    if not path.exists():
        return False
    conn = _duckdb_connect()
    try:
        rows = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
        schema = {str(row[0]): str(row[1]).upper() for row in rows}
        file_mtime_type = schema.get("file_mtime_sec", "")
        source_jsonl_type = schema.get("source_jsonl", "")
        if not any(token in file_mtime_type for token in ("DOUBLE", "FLOAT", "DECIMAL")):
            return False
        if "VARCHAR" not in source_jsonl_type:
            return False
        conn.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(path)]).fetchone()
        return True
    except Exception:
        return False
    finally:
        conn.close()




def _duckdb_materialize_parquet_sidecars_sync(force: bool = False) -> Dict[str, Any]:
    if duckdb is None:
        raise RuntimeError("duckdb dependency is not installed")
    _ensure_parquet_dir_exists()
    created_files: List[str] = []
    reused_files: List[str] = []
    skipped_files: List[str] = []
    total_bytes = 0
    for path in _duckdb_source_files():
        try:
            stat = path.stat()
        except OSError:
            continue
        if int(stat.st_size or 0) < _duckdb_stage_min_bytes():
            skipped_files.append(_path_to_app_relative(path))
            continue
        source_jsonl = _path_to_app_relative(path)
        target = _duckdb_stage_parquet_path(path, stat)
        existed = target.exists()
        if force and existed:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            existed = False
        result = _duckdb_stage_jsonl_to_parquet_sync(path, stat, source_jsonl, float(stat.st_mtime or 0.0))
        total_bytes += _safe_file_size(result)
        if existed:
            reused_files.append(_path_to_app_relative(result))
        else:
            created_files.append(_path_to_app_relative(result))
    return {
        "created_files": created_files,
        "reused_files": reused_files,
        "skipped_files": skipped_files,
        "parquet_dir": str(PARQUET_DIR),
        "parquet_files_total": _count_glob_files(PARQUET_DIR, "*.parquet"),
        "parquet_bytes_total": _sum_glob_file_sizes(PARQUET_DIR, "*.parquet"),
        "selected_bytes_total": total_bytes,
    }


def _duckdb_optional_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _duckdb_optional_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _duckdb_source_key(source_jsonl: Any) -> str:
    raw = str(source_jsonl or "").strip()
    if not raw:
        return ""
    try:
        return Path(raw).stem.strip()
    except Exception:
        tail = raw.rsplit("/", 1)[-1]
        return re.sub(r"\.jsonl$", "", tail, flags=re.IGNORECASE).strip()


def _iter_jsonl_records_with_offsets(path: Path, offset: int = 0):
    with path.open("r", encoding="utf-8", errors="replace") as file:
        file.seek(max(0, int(offset or 0)))
        while True:
            source_offset = file.tell()
            line = file.readline()
            if not line:
                break
            current_offset = file.tell()
            try:
                record = json.loads(line)
            except Exception:
                continue
            if isinstance(record, dict):
                yield source_offset, current_offset, record


def _duckdb_insert_sql() -> str:
    return """
        INSERT OR REPLACE INTO messages_raw (
            row_hash, source_jsonl, source_key, source_offset, chat_id, chat_username, chat_title,
            sender_id, sender_username, sender_name, message_id, text, date_utc,
            date_utc_raw, reply_to_msg_id, has_media, media_path, file_mtime_sec, ingested_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """


def _duckdb_flush_message_batch_sync(conn: Any, batch: List[tuple[Any, ...]]) -> None:
    if not batch:
        return
    chunk_size = min(_DUCKDB_BATCH_SIZE, max(100, _DUCKDB_EXECUTEMANY_CHUNK_SIZE))
    insert_sql = _duckdb_insert_sql()
    for start in range(0, len(batch), chunk_size):
        conn.executemany(insert_sql, batch[start : start + chunk_size])


def _duckdb_message_row_hash(source_jsonl: str, source_offset: int, record: Dict[str, Any]) -> str:
    chat = record.get("chat") if isinstance(record.get("chat"), dict) else {}
    sender = record.get("sender") if isinstance(record.get("sender"), dict) else {}
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    message_id = _duckdb_optional_int(message.get("id"))
    if message_id is not None:
        chat_identity = (
            str(chat.get("id") or "")
            or str(chat.get("username") or "")
            or str(chat.get("title") or "")
        )
        key = f"telegram-message\n{source_jsonl}\n{chat_identity}\n{message_id}"
    else:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        key = f"telegram-line\n{source_jsonl}\n{source_offset}\n{payload}"
    return hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()


def _duckdb_row_from_record(
    source_jsonl: str,
    file_mtime_sec: float,
    source_offset: int,
    record: Dict[str, Any],
) -> tuple[Any, ...]:
    chat = record.get("chat") if isinstance(record.get("chat"), dict) else {}
    sender = record.get("sender") if isinstance(record.get("sender"), dict) else {}
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    row_hash = _duckdb_message_row_hash(source_jsonl, source_offset, record)
    media_path = message.get("media_path")
    if media_path:
        media_path = str(media_path)
    return (
        row_hash,
        source_jsonl,
        _duckdb_source_key(source_jsonl),
        int(source_offset),
        _duckdb_optional_int(chat.get("id")),
        str(chat.get("username") or "") or None,
        str(chat.get("title") or "") or None,
        _duckdb_optional_int(sender.get("id")),
        str(sender.get("username") or "") or None,
        str(sender.get("name") or "") or None,
        _duckdb_optional_int(message.get("id")),
        str(message.get("text") or ""),
        _duckdb_optional_datetime(message.get("date_utc")),
        str(message.get("date_utc") or "") or None,
        _duckdb_optional_int(message.get("reply_to_msg_id")),
        bool(message.get("has_media")),
        media_path,
        float(file_mtime_sec or 0.0),
        _utc_now(),
    )


def _duckdb_duplicate_message_rows_count_sync(conn: Any) -> int:
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(duplicate_count), 0)
            FROM (
                SELECT COUNT(*) - 1 AS duplicate_count
                FROM messages_raw
                WHERE message_id IS NOT NULL
                GROUP BY source_jsonl, message_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        return int((row[0] if row else 0) or 0)
    except Exception:
        return 0


def _duckdb_deduplicate_messages_sync(conn: Any) -> int:
    rows = conn.execute(
        """
        SELECT row_hash
        FROM (
            SELECT
                row_hash,
                row_number() OVER (
                    PARTITION BY source_jsonl, message_id
                    ORDER BY source_offset DESC, ingested_at DESC
                ) AS rn
            FROM messages_raw
            WHERE message_id IS NOT NULL
        )
        WHERE rn > 1
        """
    ).fetchall()
    duplicate_hashes = [str(row[0]) for row in rows if row and row[0]]
    if not duplicate_hashes:
        return 0

    for start in range(0, len(duplicate_hashes), 1000):
        chunk = duplicate_hashes[start : start + 1000]
        placeholders = ",".join("?" for _ in chunk)
        conn.execute(f"DELETE FROM messages_raw WHERE row_hash IN ({placeholders})", chunk)
    return len(duplicate_hashes)




def _duckdb_due() -> bool:
    if duckdb is None or not _DUCKDB_SYNC_ENABLED:
        return False
    status = _duckdb_status_snapshot()
    if status.get("running"):
        return False
    last_refresh_at = status.get("last_refresh_at")
    if not last_refresh_at:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last_refresh_at))
    except Exception:
        return True
    return (_utc_now() - last_dt).total_seconds() >= max(15, _DUCKDB_SYNC_INTERVAL_SEC)


def _schedule_duckdb_live_sync_debounced(delay_sec: float = 2.0) -> bool:
    global _duckdb_live_sync_pending, _duckdb_live_sync_timer
    if duckdb is None or not _DUCKDB_SYNC_ENABLED:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    _duckdb_live_sync_pending = True
    if _duckdb_live_sync_timer is not None:
        try:
            _duckdb_live_sync_timer.cancel()
        except Exception:
            pass
        _duckdb_live_sync_timer = None

    def _flush_live_sync() -> None:
        global _duckdb_live_sync_pending, _duckdb_live_sync_timer
        _duckdb_live_sync_timer = None
        if not _duckdb_live_sync_pending:
            return
        if _schedule_duckdb_sync(force_full=False):
            _duckdb_live_sync_pending = False

    _duckdb_live_sync_timer = loop.call_later(max(0.2, float(delay_sec or 0.0)), _flush_live_sync)
    return True


async def _refresh_duckdb_async(force_full: bool = False) -> None:
    started_at = _utc_now().isoformat()
    _duckdb_update_status(
        running=True,
        progress_started_at=started_at,
        progress_log=[],
        progress_label="Подготовка DuckDB",
        current_item=None,
        last_error=None,
        derived_queued=[],
    )
    _append_runtime_log("duckdb", f"sync started: force_full={force_full}")
    try:
        ingest_result = await asyncio.to_thread(_duckdb_ingest_sync, force_full)
    except Exception as exc:
        _duckdb_update_status(
            running=False,
            last_error=str(exc),
            progress_label="Ошибка",
            current_item=None,
            stale_reason="DuckDB не смог обработать новые JSONL",
        )
        _duckdb_append_log(f"Ошибка DuckDB: {exc}")
        _append_runtime_log("duckdb", f"sync failed: {exc}")
    else:
        _duckdb_update_status(
            running=False,
            progress_label="DuckDB готов",
            current_item=None,
            next_refresh_at=_duckdb_next_refresh_at(_duckdb_status_snapshot().get("last_refresh_at")),
        )
        rows_ingested = int((ingest_result or {}).get("rows_ingested_in_run", 0) or 0)
        derived_queued = (
            _schedule_duckdb_dependent_refreshes(force_full=force_full)
            if force_full or rows_ingested > 0
            else []
        )
        if derived_queued:
            queued_text = ", ".join(derived_queued)
            _duckdb_update_status(derived_queued=derived_queued)
            _duckdb_append_log(f"Derived rebuild queued: {queued_text}")
            _append_runtime_log("duckdb", f"derived refresh queued: {queued_text}")
        else:
            _duckdb_update_status(derived_queued=[])
        _append_runtime_log("duckdb", "sync complete")
    finally:
        global _duckdb_sync_task
        _duckdb_sync_task = None
        if _duckdb_live_sync_pending:
            _schedule_duckdb_sync(force_full=False)


def _schedule_duckdb_sync(force_full: bool = False) -> bool:
    global _duckdb_sync_task
    task = _duckdb_sync_task
    if task is not None and not task.done():
        return False
    try:
        _duckdb_sync_task = asyncio.create_task(_refresh_duckdb_async(force_full=force_full))
    except RuntimeError:
        _duckdb_sync_task = None
        return False
    return True


async def _duckdb_autorefresh_loop() -> None:
    while True:
        try:
            if _duckdb_due():
                _schedule_duckdb_sync(force_full=False)
            await asyncio.sleep(_DUCKDB_LOOP_SLEEP_SEC)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[duckdb] scheduler error: {exc!r}")
            await asyncio.sleep(_DUCKDB_LOOP_SLEEP_SEC)


async def _monitor_snapshot_payload(history_points: int = 60) -> Dict[str, Any]:
    return {
        "ts": _utc_now().isoformat(),
        "runtime": (await _runtime_status()).model_dump(),
        "server": ServerRuntimeDTO(**_server_runtime_snapshot()).model_dump(),
        "system": _system_metrics_payload(history_points=history_points),
        "crm": _build_analysis_status("crm").model_dump(),
        "events": _build_analysis_status("events").model_dump(),
        "contacts": _build_analysis_status("contacts").model_dump(),
        "duckdb": _build_duckdb_status().model_dump(),
        "media": _build_media_status().model_dump(),
        "import_sync": _compute_import_sync_status().model_dump(),
    }




async def _system_metrics_loop() -> None:
    _append_runtime_log("server", "system metrics sampler started")
    while True:
        try:
            await asyncio.to_thread(_record_system_metrics_snapshot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _append_runtime_log("server", f"system metrics sampler error: {exc}")
        await asyncio.sleep(max(2.0, _SYSTEM_METRICS_INTERVAL_SEC))


def _publish_lead_event(chat_key: str, record: Dict[str, Any]) -> None:
    if not _lead_event_subscribers:
        return

    event = {
        "lead": chat_key,
        "chat": record.get("chat") or {},
        "sender": record.get("sender") or {},
        "message": record.get("message") or {},
    }

    stale_subscribers: List[asyncio.Queue] = []
    for queue in list(_lead_event_subscribers):
        try:
            queue.put_nowait(event)
        except Exception:
            stale_subscribers.append(queue)

    for queue in stale_subscribers:
        _lead_event_subscribers.discard(queue)


def _path_to_app_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(APP_DIR))
    except ValueError:
        return str(path.resolve())


def _app_relative_to_abs_path(app_relative_path: str) -> Path:
    normalized = str(app_relative_path or "").strip().lstrip("/")
    resolved = (APP_DIR / normalized).resolve()
    try:
        resolved.relative_to(APP_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный путь media") from exc
    return resolved


def _is_supported_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS


def _ocr_text_path_for_image(image_path: Path) -> Path:
    return image_path.with_suffix(".txt")


from app.services.llm_client import (
    _call_openrouter_chat_completion_sync,
    _call_openrouter_contact_qualification_sync,
    _call_openrouter_event_date_sync,
    _call_openrouter_route_address_sync,
    _normalize_openrouter_model_id,
    _record_llm_audit,
)



_DEFAULT_TELEGRAM_SCAN_GROUPS: List[Dict[str, Any]] = [
    {
        "id": "A",
        "label": "A — критичные продажи/лиды",
        "channels_range": "50–100",
        "frequency": "каждые 1–5 минут",
        "interval_minutes": 5,
    },
    {
        "id": "B",
        "label": "B — важные отраслевые",
        "channels_range": "100–200",
        "frequency": "каждые 10–30 минут",
        "interval_minutes": 30,
    },
    {
        "id": "C",
        "label": "C — фоновые",
        "channels_range": "300–500",
        "frequency": "1–4 раза в день",
        "interval_minutes": 360,
    },
    {
        "id": "D",
        "label": "D — архив/редко",
        "channels_range": "остаток",
        "frequency": "раз в сутки/неделю",
        "interval_minutes": 1440,
    },
]


def _default_telegram_scan_groups() -> List[Dict[str, Any]]:
    return [dict(item) for item in _DEFAULT_TELEGRAM_SCAN_GROUPS]


def _normalize_scan_group_id(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    return normalized[:24] if normalized else "C"


def _normalize_scan_group_assignment_key(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    return normalized


def _coerce_telegram_scan_groups(raw: Any) -> List[Dict[str, Any]]:
    defaults_by_id = {
        str(item.get("id")): dict(item)
        for item in _DEFAULT_TELEGRAM_SCAN_GROUPS
    }
    incoming = raw if isinstance(raw, list) else []
    groups_by_id: Dict[str, Dict[str, Any]] = {}

    for item in incoming:
        if not isinstance(item, dict):
            continue
        group_id = _normalize_scan_group_id(item.get("id"))
        if not group_id:
            continue
        defaults = defaults_by_id.get(group_id, {})
        try:
            interval_minutes = int(item.get("interval_minutes", defaults.get("interval_minutes", 60)))
        except (TypeError, ValueError):
            interval_minutes = int(defaults.get("interval_minutes", 60) or 60)
        groups_by_id[group_id] = {
            "id": group_id,
            "label": str(item.get("label") or defaults.get("label") or group_id).strip(),
            "channels_range": str(item.get("channels_range") or defaults.get("channels_range") or "").strip(),
            "frequency": str(item.get("frequency") or defaults.get("frequency") or "").strip(),
            "interval_minutes": max(1, min(10080, interval_minutes)),
        }

    for default in _DEFAULT_TELEGRAM_SCAN_GROUPS:
        group_id = str(default["id"])
        groups_by_id.setdefault(group_id, dict(default))

    preferred_order = [str(item["id"]) for item in _DEFAULT_TELEGRAM_SCAN_GROUPS]
    extra_ids = sorted(group_id for group_id in groups_by_id.keys() if group_id not in preferred_order)
    return [groups_by_id[group_id] for group_id in [*preferred_order, *extra_ids]]


def _coerce_telegram_scan_group_assignments(raw: Any, groups: List[Dict[str, Any]]) -> Dict[str, str]:
    valid_groups = {_normalize_scan_group_id(item.get("id")) for item in groups if isinstance(item, dict)}
    assignments: Dict[str, str] = {}
    if not isinstance(raw, dict):
        return assignments

    for raw_key, raw_group_id in raw.items():
        key = _normalize_scan_group_assignment_key(raw_key)
        group_id = _normalize_scan_group_id(raw_group_id)
        if key and group_id in valid_groups:
            assignments[key] = group_id
    return assignments


def _default_contact_qualification_prompts() -> List[Dict[str, str]]:
    return [
        {
            "id": "needs_priority",
            "title": "Потребности и покупки",
            "prompt": "проанализируй сообщения человека и оцени его потребности что человек может покупать в приоритете?",
        },
        {
            "id": "first_message",
            "title": "Первое сообщение для знакомства",
            "prompt": "оцени какое первое сообщение написать человек на основе его сообщений для того чтобы познакомиться",
        },
        {
            "id": "product_offer",
            "title": "Какой продукт предложить",
            "prompt": (
                "проанализируй сообщения человека и определи какой продукт, оффер или услугу ему стоит предложить. "
                "Верни: основной продукт, альтернативный продукт, почему это подходит, что уточнить перед продажей."
            ),
        },
    ]


def _normalize_contact_prompt_id(value: Any, title: str = "", prompt: str = "") -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_-]+", "_", raw).strip("_")
    if raw:
        return raw[:80]
    source = f"{title}\n{prompt}".strip() or "prompt"
    return hashlib.sha1(source.encode("utf-8", errors="ignore")).hexdigest()[:12]


from app.core.app_settings import (
    _coerce_app_settings,
    _coerce_contact_qualification_prompts,
    _coerce_llm_answer_prompts,
    _contact_prompt_by_id,
    _default_app_settings,
    _default_llm_answer_prompts,
    _get_app_settings,
    _save_app_settings,
    _select_llm_answer_prompt,
)


from app.services.license_runtime import *  # compatibility facade

def _media_ocr_images_enabled() -> bool:
    return bool(_get_app_settings().get("ocr_images_enabled", False))


def _media_ocr_delete_images_enabled() -> bool:
    return bool(_get_app_settings().get("ocr_delete_images_after_processing", False))


def _ocr_mode() -> str:
    if _ocr_service_url():
        return "service"
    if OCR_LOCAL_FALLBACK:
        return "local"
    return "disabled"


def _ocr_is_enabled() -> bool:
    return _media_ocr_images_enabled() and _ocr_mode() != "disabled"


def _ocr_relative_image_path(image_path: Path) -> str:
    return str(image_path.resolve().relative_to(PAYME_OUT_DIR.resolve()))


from app.services.media_assets import (
    _build_media_status,
    _call_ocr_service_sync,
    _ensure_pending_image_ocr_task,
    _find_media_record_for_image_sync,
    _image_ocr_progress_log,
    _is_media_enabled_for_chat,
    _list_image_assets,
    _media_backfill_summary,
)



def _load_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is not None:
        return _easyocr_reader

    with _easyocr_reader_lock:
        if _easyocr_reader is not None:
            return _easyocr_reader

        import easyocr

        _easyocr_reader = easyocr.Reader(["ru", "en"], gpu=False)
        return _easyocr_reader


def _normalize_ocr_lines(lines: List[Any]) -> str:
    normalized: List[str] = []
    for item in lines:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return "\n".join(normalized).strip()


def _ocr_image_file_sync(image_path: Path, force: bool = False) -> Optional[Path]:
    if not _is_supported_image_file(image_path):
        return None

    txt_path = _ocr_text_path_for_image(image_path)
    if txt_path.exists() and not force:
        return txt_path

    mode = _ocr_mode()
    if mode == "service":
        return _call_ocr_service_sync(image_path, force=force)
    if mode == "local":
        reader = _load_easyocr_reader()
        lines = reader.readtext(str(image_path), detail=0, paragraph=True)
        recognized_text = _normalize_ocr_lines(list(lines))
        txt_path.write_text(recognized_text, encoding="utf-8")
        return txt_path
    raise RuntimeError("OCR backend is disabled. Start gramlead-ocr or set PAYME_OCR_LOCAL_FALLBACK=1.")


async def _ocr_image_file(image_path: Path, force: bool = False) -> Optional[Path]:
    return await asyncio.to_thread(_ocr_image_file_sync, image_path, force)


def _check_ocr_backend_ready_sync() -> tuple[bool, Optional[str]]:
    mode = _ocr_mode()
    if mode == "disabled":
        return False, "OCR отключён. Поднимите отдельный сервис gramlead-ocr."
    if mode == "local":
        try:
            _load_easyocr_reader()
            return True, None
        except Exception as exc:
            return False, f"Локальный OCR недоступен: {exc}"
    try:
        service_url = _ocr_service_url()
        if not service_url:
            return False, "OCR service URL не указан. Укажите адрес gramlead-ocr в настройках."
        response = requests.get(f"{service_url}/health", timeout=OCR_HEALTH_TIMEOUT_SEC)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok", True):
            return False, str(payload.get("message") or "OCR service returned not ready")
        if payload.get("reader_loaded"):
            return True, None
        if payload.get("reader_error"):
            return False, f"OCR service model error: {payload.get('reader_error')}"
        try:
            requests.post(f"{service_url}/warmup", timeout=OCR_WARMUP_TIMEOUT_SEC)
        except Exception:
            pass
        if payload.get("reader_loading"):
            return False, "OCR service прогревает EasyOCR-модели. Распознавание начнётся автоматически после прогрева."
        return False, "OCR service ещё не прогрет. Запущен прогрев EasyOCR-моделей."
    except Exception as exc:
        return False, f"OCR service недоступен: {exc}"


def _iter_media_image_files() -> List[Path]:
    result: List[Path] = []
    if not PAYME_OUT_DIR.exists():
        return result

    for media_dir in PAYME_OUT_DIR.glob("*/media"):
        if not media_dir.is_dir():
            continue
        for path in media_dir.iterdir():
            if _is_supported_image_file(path):
                result.append(path)

    result.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return result


def _iter_media_text_files() -> List[Path]:
    result: List[Path] = []
    if not PAYME_OUT_DIR.exists():
        return result

    for media_dir in PAYME_OUT_DIR.glob("*/media"):
        if not media_dir.is_dir():
            continue
        for path in media_dir.iterdir():
            if path.is_file() and path.suffix.lower() == ".txt":
                result.append(path)

    result.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return result


def _count_pending_image_ocr_files() -> int:
    pending = 0
    for image_path in _iter_media_image_files():
        if not _ocr_text_path_for_image(image_path).exists():
            pending += 1
    return pending








def _normalize_media_lead(value: Union[str, int]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    return normalized


def _get_media_sync_state() -> Dict[str, Any]:
    current = telegram_sync.state.get("_media_sync")
    if not isinstance(current, dict):
        current = {}
    leads: List[str] = []
    seen: set[str] = set()
    for item in current.get("selected_leads") or []:
        lead = _normalize_media_lead(item)
        if not lead or lead in seen:
            continue
        seen.add(lead)
        leads.append(lead)
    current["selected_leads"] = leads
    telegram_sync.state["_media_sync"] = current
    return current


def _get_media_selected_leads() -> List[str]:
    return list(_get_media_sync_state().get("selected_leads") or [])


def _set_media_selected_leads(leads: List[str]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for item in leads:
        lead = _normalize_media_lead(item)
        if not lead or lead in seen:
            continue
        seen.add(lead)
        normalized.append(lead)
    state = _get_media_sync_state()
    state["selected_leads"] = normalized
    telegram_sync.state["_media_sync"] = state
    telegram_sync.save_state()
    return normalized




def _jur_entities_channel_key() -> str:
    return str(JUR_ENTITIES_CHANNEL or "baza_directorov").strip().lstrip("@").lower() or "baza_directorov"


def _get_jur_entities_state() -> Dict[str, Any]:
    current = telegram_sync.state.get("_jur_entities")
    if not isinstance(current, dict):
        current = {}
    items = current.get("items")
    if not isinstance(items, list):
        items = []
    parser_selected = current.get("parser_selected")
    if not isinstance(parser_selected, list):
        parser_selected = []
    current["items"] = items
    current["parser_selected"] = [str(item).strip() for item in parser_selected if str(item or "").strip()]
    current.setdefault("last_sync_at", None)
    current.setdefault("last_error", None)
    telegram_sync.state["_jur_entities"] = current
    return current


def _get_jur_entities_parser_selected() -> List[str]:
    return list(_get_jur_entities_state().get("parser_selected") or [])


def _set_jur_entities_parser_selected(keys: List[str]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for item in keys:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    state = _get_jur_entities_state()
    state["parser_selected"] = normalized
    telegram_sync.state["_jur_entities"] = state
    telegram_sync.save_state()
    return normalized


def _set_jur_entities_items(items: List[Dict[str, Any]], last_error: Optional[str] = None) -> None:
    state = _get_jur_entities_state()
    state["items"] = items
    state["last_sync_at"] = _utc_now().isoformat()
    state["last_error"] = last_error
    telegram_sync.state["_jur_entities"] = state
    telegram_sync.save_state()


def _safe_jur_entities_file_name(value: str, default_ext: str = ".xlsx") -> str:
    raw = str(value or "").strip()
    if not raw:
        return f"document{default_ext}"
    normalized = re.sub(r"[^\w.\-]+", "_", raw, flags=re.UNICODE).strip("._")
    if not normalized:
        normalized = f"document{default_ext}"
    suffix = Path(normalized).suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        normalized += default_ext
    return normalized


def _jur_entities_caption_preview(message_text: Optional[str]) -> Optional[str]:
    text = str(message_text or "").strip()
    if not text:
        return None
    return text


def _jur_entity_row_from_state(item: Dict[str, Any], parser_selected: set[str]) -> "JurEntityFileDTO":
    file_path = str(item.get("file_path") or "").strip()
    normalized_file_path = "/" + file_path.lstrip("/") if file_path else ""
    return JurEntityFileDTO(
        file_key=str(item.get("file_key") or ""),
        message_id=int(item.get("message_id") or 0),
        channel=str(item.get("channel") or _jur_entities_channel_key()),
        file_name=str(item.get("file_name") or ""),
        file_path=normalized_file_path,
        size_bytes=int(item.get("size_bytes") or 0),
        message_date_utc=str(item.get("message_date_utc") or "") or None,
        caption_preview=str(item.get("caption_preview") or "") or None,
        parser_enabled=str(item.get("file_key") or "") in parser_selected,
        downloaded_at=str(item.get("downloaded_at") or "") or None,
        structure_common=bool(item.get("structure_common")),
        structure_label=str(item.get("structure_label") or "") or None,
        structure_tone=str(item.get("structure_tone") or "") or None,
        structure_summary=str(item.get("structure_summary") or "") or None,
        structure_group_count=int(item.get("structure_group_count") or 0),
    )


def _list_jur_entities_rows(
    query: str = "",
    parser_filter: str = "all",
) -> List["JurEntityFileDTO"]:
    state = _get_jur_entities_state()
    parser_selected = set(_get_jur_entities_parser_selected())
    structure_map = analyze_jur_entity_structures(
        state.get("items") or [],
        app_dir=APP_DIR,
        cache_path=JUR_ENTITIES_DIR / ".structure-cache.json",
    )
    normalized_query = str(query or "").strip().lower()
    normalized_parser_filter = str(parser_filter or "all").strip().lower()

    rows: List[JurEntityFileDTO] = []
    for item in state.get("items") or []:
        if not isinstance(item, dict):
            continue
        merged_item = dict(item)
        merged_item.update(structure_map.get(str(item.get("file_key") or ""), {}))
        row = _jur_entity_row_from_state(merged_item, parser_selected)
        if normalized_parser_filter == "selected" and not row.parser_enabled:
            continue
        if normalized_parser_filter == "unselected" and row.parser_enabled:
            continue
        if normalized_query:
            haystack = " ".join(
                [
                    row.file_name,
                    row.channel,
                    row.caption_preview or "",
                    row.file_path,
                ]
            ).lower()
            if normalized_query not in haystack:
                continue
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row.message_date_utc or "",
            row.message_id,
        ),
        reverse=True,
    )
    return rows


async def _resolve_jur_entities_channel_entity(dialogs_client: TelegramClient) -> Any:
    selector = _jur_entities_channel_key()
    try:
        return await dialogs_client.get_entity(selector)
    except Exception:
        pass

    async for dialog in dialogs_client.iter_dialogs(ignore_migrated=True):
        entity = getattr(dialog, "entity", None)
        if entity is None:
            continue
        username = str(getattr(entity, "username", "") or "").strip().lower()
        title = str(getattr(entity, "title", "") or getattr(dialog, "name", "") or "").strip().lower()
        if username == selector or title == selector:
            return entity

    raise HTTPException(status_code=404, detail=f"Канал '{selector}' не найден в Telegram-сессии")


async def _sync_jur_entities_xlsx() -> "JurEntitySyncDTO":
    session_file = _telegram_session_file_path()
    if not session_file.exists():
        raise HTTPException(status_code=400, detail="Telegram не авторизован")
    if telegram_sync.is_sync_paused():
        status = telegram_sync.get_sync_control_status()
        raise HTTPException(
            status_code=429,
            detail=f"Telegram sync приостановлен: {status.get('reason') or 'manual'}",
        )
    if telegram_sync._is_global_flood_wait_active("jur entities xlsx"):
        status = telegram_sync.get_global_flood_wait_status()
        raise HTTPException(
            status_code=429,
            detail=f"Telegram cooldown активен до {status.get('can_fetch_after') or status.get('until')}",
        )
    if telegram_sync._is_operation_cooldown_active("dialogs", "jur entities xlsx"):
        status = telegram_sync.get_rate_limit_status()
        cooldown = (status.get("operation_cooldowns") or {}).get("dialogs") or {}
        raise HTTPException(
            status_code=429,
            detail=f"Telegram dialogs cooldown активен до {cooldown.get('can_fetch_after') or cooldown.get('retry_after')}",
        )

    JUR_ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
    channel_dir = JUR_ENTITIES_DIR / _jur_entities_channel_key()
    channel_dir.mkdir(parents=True, exist_ok=True)

    temp_session_dir = APP_DIR / ".tmp"
    temp_session_dir.mkdir(parents=True, exist_ok=True)
    temp_session_base = temp_session_dir / f"jur-entities-{uuid.uuid4().hex}"
    temp_session_file = temp_session_base.with_suffix(".session")
    temp_session_journal = temp_session_file.with_name(f"{temp_session_file.name}-journal")
    source_journal = session_file.with_name(f"{session_file.name}-journal")

    try:
        shutil.copy2(session_file, temp_session_file)
        if source_journal.exists():
            shutil.copy2(source_journal, temp_session_journal)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось подготовить временную Telegram-сессию: {exc}") from exc

    current_items = {
        str(item.get("file_key")): item
        for item in (_get_jur_entities_state().get("items") or [])
        if isinstance(item, dict) and str(item.get("file_key") or "").strip()
    }

    dialogs_client: Optional[TelegramClient] = None
    downloaded_count = 0
    reused_count = 0
    next_items: List[Dict[str, Any]] = []

    await telegram_sync._sleep_operation_cooldown("dialogs", "jur entities xlsx")
    await telegram_sync._dialogs_lock.acquire()
    try:
        api_id, api_hash = _require_telegram_api_credentials()
        dialogs_client = TelegramClient(str(temp_session_base), api_id, api_hash)
        await dialogs_client.connect()
        if not await dialogs_client.is_user_authorized():
            raise HTTPException(status_code=400, detail="Telegram не авторизован")

        entity = await _resolve_jur_entities_channel_entity(dialogs_client)

        async for msg in dialogs_client.iter_messages(entity, reverse=False):
            document = getattr(msg, "document", None)
            file_info = getattr(msg, "file", None)
            if document is None or file_info is None:
                continue

            original_name = str(getattr(file_info, "name", "") or "").strip()
            ext = Path(original_name).suffix.lower() or str(getattr(file_info, "ext", "") or "").lower()
            if ext not in {".xlsx", ".xls"}:
                continue

            safe_name = _safe_jur_entities_file_name(original_name or f"{msg.id}{ext}", default_ext=ext or ".xlsx")
            target_path = channel_dir / f"{msg.id}_{safe_name}"
            file_key = str(int(msg.id))
            existing = current_items.get(file_key) or {}

            if target_path.exists():
                reused_count += 1
            else:
                try:
                    saved_path = await dialogs_client.download_media(msg, file=str(target_path))
                except Exception as exc:
                    print(f"[jur-entities] xlsx download error for message {msg.id}: {exc!r}")
                    continue
                if saved_path:
                    target_path = Path(saved_path).resolve()
                downloaded_count += 1

            try:
                stat = target_path.stat()
                size_bytes = int(stat.st_size)
            except OSError:
                size_bytes = int(existing.get("size_bytes") or 0)

            msg_date_utc = msg.date.astimezone(timezone.utc).isoformat() if getattr(msg, "date", None) else None
            next_items.append(
                {
                    "file_key": file_key,
                    "message_id": int(msg.id),
                    "channel": _jur_entities_channel_key(),
                    "file_name": original_name or target_path.name,
                    "file_path": _path_to_app_relative(target_path),
                    "size_bytes": size_bytes,
                    "message_date_utc": msg_date_utc,
                    "caption_preview": _jur_entities_caption_preview(getattr(msg, "message", None)),
                    "downloaded_at": _utc_now().isoformat(),
                }
            )
    except HTTPException:
        raise
    except FloodWaitError as exc:
        telegram_sync._activate_global_flood_wait(exc, "jur entities xlsx")
        raise HTTPException(status_code=429, detail=f"Telegram FloodWait: ждать {telegram_sync._flood_wait_seconds(exc)} секунд") from exc
    except (PeerFloodError, UserPrivacyRestrictedError) as exc:
        telegram_sync._mark_telegram_risk_blocked(exc, "jur entities xlsx")
        raise HTTPException(status_code=429, detail=f"Telegram ограничил запрос XLSX: {type(exc).__name__}") from exc
    except Exception as exc:
        if telegram_sync._is_transient_telegram_rate_limit(exc):
            telegram_sync._register_telegram_transient_limit(exc, "jur entities xlsx", operation="dialogs")
            raise HTTPException(status_code=429, detail=f"Telegram dialogs cooldown: {exc}") from exc
        _set_jur_entities_items(_get_jur_entities_state().get("items") or [], last_error=str(exc))
        raise HTTPException(status_code=500, detail=f"Не удалось загрузить XLSX из Telegram: {exc}") from exc
    finally:
        try:
            telegram_sync._dialogs_lock.release()
        except ValueError:
            pass
        if dialogs_client is not None:
            try:
                await dialogs_client.disconnect()
            except Exception:
                pass
        for path in (temp_session_file, temp_session_journal):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    next_items.sort(
        key=lambda item: (
            str(item.get("message_date_utc") or ""),
            int(item.get("message_id") or 0),
        ),
        reverse=True,
    )
    _set_jur_entities_items(next_items, last_error=None)
    return JurEntitySyncDTO(
        ok=True,
        message=f"XLSX из канала '{_jur_entities_channel_key()}' синхронизированы",
        channel=_jur_entities_channel_key(),
        total_items=len(next_items),
        downloaded_count=downloaded_count,
        reused_count=reused_count,
        last_sync_at=_get_jur_entities_state().get("last_sync_at"),
        sync_error=None,
    )


def _delete_non_image_media_files() -> int:
    deleted = 0
    if not PAYME_OUT_DIR.exists():
        return deleted

    for media_dir in PAYME_OUT_DIR.glob("*/media"):
        if not media_dir.is_dir():
            continue
        for path in media_dir.iterdir():
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in _IMAGE_EXTENSIONS or suffix == ".txt":
                continue
            try:
                path.unlink(missing_ok=True)
                deleted += 1
            except OSError:
                continue
    return deleted


def _clear_media_for_lead(lead: str) -> Dict[str, int]:
    deleted_images = 0
    deleted_texts = 0
    target = _normalize_media_lead(lead)
    if not target:
        return {"deleted_images": 0, "deleted_texts": 0}

    media_dir = PAYME_OUT_DIR / target / "media"
    if not media_dir.exists():
        for candidate in PAYME_OUT_DIR.glob("*/media"):
            if candidate.parent.name.lower() == target:
                media_dir = candidate
                break

    if not media_dir.exists() or not media_dir.is_dir():
        return {"deleted_images": 0, "deleted_texts": 0}

    for path in list(media_dir.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in _IMAGE_EXTENSIONS:
            txt_path = _ocr_text_path_for_image(path)
            try:
                path.unlink(missing_ok=True)
                deleted_images += 1
            except OSError:
                pass
            if txt_path.exists():
                try:
                    txt_path.unlink(missing_ok=True)
                    deleted_texts += 1
                except OSError:
                    pass
        elif suffix == ".txt":
            try:
                path.unlink(missing_ok=True)
                deleted_texts += 1
            except OSError:
                pass

    return {
        "deleted_images": deleted_images,
        "deleted_texts": deleted_texts,
    }


def _clear_all_media_images() -> Dict[str, int]:
    deleted_images = 0
    deleted_texts = 0
    for media_dir in PAYME_OUT_DIR.glob("*/media"):
        if not media_dir.is_dir():
            continue
        result = _clear_media_for_lead(media_dir.parent.name)
        deleted_images += int(result.get("deleted_images", 0))
        deleted_texts += int(result.get("deleted_texts", 0))
    return {
        "deleted_images": deleted_images,
        "deleted_texts": deleted_texts,
    }


def _media_image_message_id(image_path: Path) -> int:
    match = re.search(r"\d+", image_path.stem)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            pass
    digest = hashlib.sha1(str(image_path).encode("utf-8", errors="ignore")).hexdigest()[:10]
    return int(digest, 16)




def _crm_contact_from_media_ocr_text(image_path: Path, ocr_text: str) -> Optional["CrmContactDTO"]:
    text = str(ocr_text or "").strip()
    if not text:
        return None

    rec = _find_media_record_for_image_sync(image_path)
    lead_name = image_path.parent.parent.name
    source_selector = _managed_selector_map().get(lead_name.lower())
    msg = dict(rec.get("message", {}) or {})
    original_text = str(msg.get("text") or "").strip()
    combined_text = "\n".join(item for item in [original_text, text] if item).strip()
    msg["text"] = combined_text
    msg["has_media"] = True
    msg["media_path"] = "/" + _path_to_app_relative(image_path).lstrip("/")
    rec = {
        "chat": rec.get("chat") or {},
        "sender": rec.get("sender") or {},
        "message": msg,
    }
    row = _crm_extract_contact_from_record(lead_name, source_selector, rec)
    if not row:
        return None
    row.match_sources = _crm_unique_list([*row.match_sources, "media", "ocr"])
    row.field_provenance = dict(row.field_provenance or {})
    for field in list(row.field_provenance.keys()):
        _crm_add_field_provenance(row.field_provenance, field, "media.ocr", _path_to_app_relative(image_path))
    row.text = combined_text
    return row


def _upsert_media_crm_contact_sync(row: "CrmContactDTO", image_path: Path) -> bool:
    row_key = f"{_crm_row_key(row.model_dump())}:media:{hashlib.sha1(str(image_path).encode('utf-8', errors='ignore')).hexdigest()[:10]}"
    if duckdb is not None:
        _duckdb_init_schema_sync()
        conn = _duckdb_connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO crm_contacts (
                    row_key, lead, source_selector, message_id, date_utc_raw, text,
                    sender_username, sender_name, full_name, first_name, last_name, patronymic,
                    name_components_count, job_title, companies_json, phones_json, emails_json,
                    city, match_sources_json, field_provenance_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _duckdb_crm_row_payload(row, row_key=row_key),
            )
            count_row = conn.execute("SELECT COUNT(*) FROM crm_contacts").fetchone()
            crm_total_rows = int(count_row[0] or 0) if count_row else 0
        finally:
            conn.close()
        state = _analysis_state("crm")
        state["duckdb_ready"] = True
        state["total_rows"] = max(int(state.get("total_rows", 0) or 0), crm_total_rows)
        state["last_refresh_at"] = _utc_now().isoformat()
        state["last_error"] = None
        telegram_sync.save_state()
        return True

    rows = _load_analysis_cache_rows("crm")
    row_dict = row.model_dump()
    row_dict["_row_key"] = row_key
    rows_by_key = {str(item.get("_row_key") or _crm_row_key(item)): item for item in rows if isinstance(item, dict)}
    rows_by_key[row_key] = row_dict
    merged = list(rows_by_key.values())
    merged.sort(key=lambda item: (str(item.get("date_utc") or ""), int(item.get("message_id") or 0)), reverse=True)
    _save_analysis_cache_rows("crm", merged)
    state = _analysis_state("crm")
    state["total_rows"] = len(merged)
    state["last_refresh_at"] = _utc_now().isoformat()
    state["last_error"] = None
    telegram_sync.save_state()
    return True


def _media_ocr_crm_fields_from_text(text: str) -> List[Dict[str, str]]:
    raw_text = str(text or "").strip()
    if not raw_text:
        return []

    row = _crm_extract_contact_from_record(
        "media",
        "media",
        {
            "chat": {"username": "media", "title": "media"},
            "sender": {},
            "message": {
                "id": 0,
                "text": raw_text,
                "date_utc": _utc_now().isoformat(),
            },
        },
    )
    if not row:
        return []

    fields: List[Dict[str, str]] = []
    if row.full_name:
        fields.append({"field_type": "fio", "field_label": _outreach_field_label("fio"), "value": row.full_name})
    if row.job_title:
        fields.append({"field_type": "job_title", "field_label": _outreach_field_label("job_title"), "value": row.job_title})
    for company in row.companies:
        fields.append({"field_type": "company", "field_label": _outreach_field_label("company"), "value": company})
    for phone in row.phones:
        fields.append({"field_type": "contact", "field_label": _outreach_field_label("contact"), "value": phone})
    for email in row.emails:
        fields.append({"field_type": "contact", "field_label": _outreach_field_label("contact"), "value": email})
    if row.city:
        fields.append({"field_type": "city", "field_label": _outreach_field_label("city"), "value": row.city})

    unique_fields: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field in fields:
        key = (str(field.get("field_type") or ""), str(field.get("value") or ""))
        if key in seen or not key[1]:
            continue
        seen.add(key)
        unique_fields.append(field)
    return unique_fields


def _process_media_image_file_sync(image_path: Path, force: bool = False) -> Dict[str, int]:
    if not _is_supported_image_file(image_path):
        return {"processed_count": 0, "error_count": 0, "crm_rows_created": 0, "deleted_images": 0}
    if not image_path.exists():
        return {"processed_count": 0, "error_count": 0, "crm_rows_created": 0, "deleted_images": 0}

    txt_path = _ocr_image_file_sync(image_path, force=force)
    if not txt_path or not txt_path.exists():
        return {"processed_count": 0, "error_count": 1, "crm_rows_created": 0, "deleted_images": 0}

    try:
        ocr_text = txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        ocr_text = ""

    crm_rows_created = 0
    crm_row = _crm_contact_from_media_ocr_text(image_path, ocr_text)
    if crm_row and _upsert_media_crm_contact_sync(crm_row, image_path):
        crm_rows_created = 1

    deleted_images = 0
    if _media_ocr_delete_images_enabled():
        try:
            image_path.unlink(missing_ok=True)
            deleted_images = 1
        except OSError as exc:
            _image_ocr_progress_log(f"Не удалось удалить изображение {image_path.name}: {exc}")

    return {
        "processed_count": 1,
        "error_count": 0,
        "crm_rows_created": crm_rows_created,
        "deleted_images": deleted_images,
    }


def _process_pending_image_ocr_sync(force: bool = False) -> Dict[str, int]:
    processed_count = 0
    error_count = 0
    crm_rows_created = 0
    deleted_images = 0
    image_paths = _iter_media_image_files()
    total = len(image_paths)
    _image_ocr_status["pending_count"] = _count_pending_image_ocr_files()
    _image_ocr_status["progress_total"] = total
    for index, image_path in enumerate(image_paths, start=1):
        txt_path = _ocr_text_path_for_image(image_path)
        _image_ocr_status["current_item"] = image_path.name
        _image_ocr_status["last_media_path"] = "/" + _path_to_app_relative(image_path).lstrip("/")
        _image_ocr_status["progress_current"] = index - 1
        _image_ocr_status["progress_percent"] = round(((index - 1) / total) * 100.0, 2) if total else 0.0
        _image_ocr_progress_log(f"Обрабатываю media OCR: {image_path.parent.parent.name}/{image_path.name}")
        try:
            result = _process_media_image_file_sync(image_path, force=force or not txt_path.exists())
            processed_count += int(result.get("processed_count", 0) or 0)
            error_count += int(result.get("error_count", 0) or 0)
            crm_rows_created += int(result.get("crm_rows_created", 0) or 0)
            deleted_images += int(result.get("deleted_images", 0) or 0)
            _image_ocr_status["processed_count"] = int(_image_ocr_status.get("processed_count", 0) or 0) + int(result.get("processed_count", 0) or 0)
            _image_ocr_status["error_count"] = int(_image_ocr_status.get("error_count", 0) or 0) + int(result.get("error_count", 0) or 0)
            _image_ocr_status["crm_rows_created"] = int(_image_ocr_status.get("crm_rows_created", 0) or 0) + int(result.get("crm_rows_created", 0) or 0)
            _image_ocr_status["deleted_images"] = int(_image_ocr_status.get("deleted_images", 0) or 0) + int(result.get("deleted_images", 0) or 0)
        except Exception as exc:
            error_count += 1
            _image_ocr_status["error_count"] = int(_image_ocr_status.get("error_count", 0) or 0) + 1
            print(f"[ocr] failed for {image_path}: {exc!r}")
        _image_ocr_status["progress_current"] = index
        _image_ocr_status["progress_percent"] = round((index / total) * 100.0, 2) if total else 100.0
    return {
        "processed_count": processed_count,
        "error_count": error_count,
        "crm_rows_created": crm_rows_created,
        "deleted_images": deleted_images,
    }


async def _run_pending_image_ocr(force: bool = False) -> None:
    _image_ocr_status["running"] = True
    _image_ocr_status["last_started_at"] = _utc_now().isoformat()
    _image_ocr_status["last_error"] = None
    _image_ocr_status["mode"] = _ocr_mode()
    _image_ocr_status["progress_current"] = 0
    _image_ocr_status["pending_count"] = max(0, _count_pending_image_ocr_files())
    _image_ocr_status["progress_total"] = max(0, len(_iter_media_image_files()))
    _image_ocr_status["progress_percent"] = 0.0
    _image_ocr_status["current_item"] = None
    _image_ocr_status["last_media_path"] = None
    _image_ocr_status["progress_log"] = []
    _image_ocr_progress_log("Запущена фоновая OCR-обработка изображений.")
    ready, reason = await asyncio.to_thread(_check_ocr_backend_ready_sync)
    _image_ocr_status["available"] = bool(ready)
    if not ready:
        _image_ocr_status["last_error"] = reason
        _image_ocr_status["running"] = False
        _image_ocr_status["last_finished_at"] = _utc_now().isoformat()
        _image_ocr_progress_log(str(reason or "OCR backend недоступен"))
        return
    try:
        result = await asyncio.to_thread(_process_pending_image_ocr_sync, force)
        _image_ocr_status["processed_count"] = int(result.get("processed_count", 0))
        _image_ocr_status["error_count"] = int(result.get("error_count", 0))
        _image_ocr_status["crm_rows_created"] = int(result.get("crm_rows_created", 0))
        _image_ocr_status["deleted_images"] = int(result.get("deleted_images", 0))
        _image_ocr_status["pending_count"] = max(0, _count_pending_image_ocr_files())
        total = max(
            int(_image_ocr_status.get("progress_total", 0) or 0),
            int(result.get("processed_count", 0) or 0) + int(result.get("error_count", 0) or 0),
        )
        current = min(total, int(result.get("processed_count", 0) or 0) + int(result.get("error_count", 0) or 0))
        _image_ocr_status["progress_total"] = total
        _image_ocr_status["progress_current"] = current
        _image_ocr_status["progress_percent"] = round((current / total) * 100.0, 2) if total > 0 else 0.0
        _image_ocr_progress_log(
            f"OCR завершён: обработано {int(result.get('processed_count', 0) or 0)}, CRM-строк {int(result.get('crm_rows_created', 0) or 0)}, удалено изображений {int(result.get('deleted_images', 0) or 0)}, ошибок {int(result.get('error_count', 0) or 0)}."
        )
    except Exception as exc:
        _image_ocr_status["last_error"] = str(exc)
        _image_ocr_progress_log(f"OCR завершился с ошибкой: {exc}")
        print(f"[ocr] background scan failed: {exc!r}")
    finally:
        _image_ocr_status["running"] = False
        _image_ocr_status["current_item"] = None
        _image_ocr_status["last_finished_at"] = _utc_now().isoformat()




async def _media_ocr_background_loop() -> None:
    _append_runtime_log("media", "media OCR background loop started")
    while True:
        try:
            if _media_ocr_images_enabled() and _ocr_is_enabled():
                for chat_key in _get_media_selected_leads():
                    entity = telegram_sync.entities_by_chat_key.get(chat_key)
                    if entity is not None:
                        telegram_sync.start_media_backfill_in_background(entity, chat_key)
                if _iter_media_image_files():
                    _ensure_pending_image_ocr_task(force=False)
            await asyncio.sleep(max(5.0, MEDIA_OCR_LOOP_INTERVAL_SEC))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _image_ocr_status["last_error"] = str(exc)
            _image_ocr_progress_log(f"Фоновый OCR loop: {exc}")
            await asyncio.sleep(max(5.0, MEDIA_OCR_LOOP_INTERVAL_SEC))


def print(*args, **kwargs):
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    file = kwargs.get("file")
    message = sep.join(str(arg) for arg in args)
    if end and message.endswith(end):
        normalized = message[: -len(end)]
    else:
        normalized = message
    source = "stderr" if file is sys.stderr else "stdout"
    if normalized:
        _append_runtime_log(source, normalized)
    builtins.print(*args, **kwargs)


class _RuntimeLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        if message:
            _append_runtime_log(record.name, message)


def _install_runtime_log_handler() -> None:
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    logger_names = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")
    for logger_name in logger_names:
        logger = logging.getLogger(logger_name)
        if any(isinstance(handler, _RuntimeLogHandler) for handler in logger.handlers):
            continue
        handler = _RuntimeLogHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)


_install_runtime_log_handler()


from app.services.telegram_sync_runtime import TelegramSync, refresh_legacy_globals, telegram_sync

_startup_retry_sec = float(os.environ.get("PAYME_STARTUP_RETRY_SEC", "5"))
_tg_bootstrap_task: Optional[asyncio.Task] = None


async def _bootstrap_telegram_sync() -> None:
    while True:
        try:
            await asyncio.to_thread(check_license)
            print("[security] license check passed")
            break
        except asyncio.CancelledError:
            raise
        except LicenseNetworkError as exc:
            print(f"[security] {exc} - retry in {_startup_retry_sec}s")
            await asyncio.sleep(_startup_retry_sec)
        except SystemExit as exc:
            print(f"[security] startup blocked: {exc}")
            return
        except Exception as exc:
            print(f"[security] unexpected startup error: {exc!r} - retry in {_startup_retry_sec}s")
            await asyncio.sleep(_startup_retry_sec)

    while True:
        try:
            await telegram_sync.start(sync_in_background=True)
            print("[telegram-sync] startup ready")
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[telegram-sync] startup failed: {exc!r} - retry in {_startup_retry_sec}s")
            await asyncio.sleep(_startup_retry_sec)

Stage = Literal["Новый","Квалификация","Демонстрация","Обсуждение","Договор","Победа","Проигрыш"]




from app.schemas.models import (
    AnalysisActionDTO,
    AnalysisConfigPayload,
    AnalysisStatusDTO,
    AppSettingsDTO,
    AppSettingsPayload,
    BackgroundTaskStatusDTO,
    ChatAnalysisHistoryDTO,
    ChatAnalysisPayload,
    ChatAnalysisRunDTO,
    ChatTokenSenderDTO,
    ChatTokenStatsDTO,
    ContactDoNotContactActionDTO,
    ContactDoNotContactPayload,
    ContactQualificationDTO,
    ContactQualificationPromptDTO,
    ContactQualificationPromptsDTO,
    ContactQualificationRequestDTO,
    ContactQualificationsDTO,
    CrmContactDTO,
    CrmContactsPageDTO,
    Deal,
    DuckDbActionDTO,
    DuckDbExportDTO,
    DuckDbLegacyCacheCleanupDTO,
    DuckDbParquetSidecarsDTO,
    DuckDbStatusDTO,
    EventKeywordsDTO,
    EventKeywordsPayload,
    EventMessageDTO,
    EventMessageDeleteDTO,
    EventMessageDeletePayload,
    EventMessagesPageDTO,
    ImageAssetDTO,
    ImageAssetTextDTO,
    ImageAssetsPageDTO,
    ImageOcrActionDTO,
    ImportSyncActionDTO,
    ImportSyncStatusDTO,
    JurEntityActionDTO,
    JurEntityActionPayload,
    JurEntityFileDTO,
    JurEntityFilesPageDTO,
    JurEntitySyncDTO,
    Lead,
    LeadActionDTO,
    LeadActionPayload,
    LeadDTO,
    LeadGroupActionDTO,
    LeadGroupPayload,
    LeadsPageDTO,
    LlmRunPayload,
    MediaClearDTO,
    MediaConfigDTO,
    MediaLeadPayload,
    MediaLeadsPayload,
    MediaStatusDTO,
    Message,
    MessageDTO,
    MessageIn,
    MessageOut,
    OpenRouterModelDTO,
    OpenRouterModelsDTO,
    OutreachCrmFieldActionDTO,
    OutreachCrmFieldDTO,
    OutreachCrmFieldPayload,
    OutreachCrmFieldsPageDTO,
    Profile,
    RouteGeocodePayload,
    RuntimeLogDTO,
    RuntimeStatusDTO,
    SearchContextDTO,
    SearchMessageDTO,
    SearchMessagesPageDTO,
    SendPayload,
    ServerRuntimeDTO,
    SourceEditDTO,
    SourcePolicyActionDTO,
    SourcePolicyDTO,
    SourcePolicyPageDTO,
    SourcePolicyPayload,
    SourceSelectorPayload,
    Stage,
    SystemMetricPointDTO,
    SystemMetricsDTO,
    TelegramApiCredentialsPayload,
    TelegramAuthActionDTO,
    TelegramAuthCodePayload,
    TelegramAuthPasswordPayload,
    TelegramAuthPhonePayload,
    TelegramAuthPhoneResendPayload,
    TelegramContactChatFilterDTO,
    TelegramContactChatFiltersDTO,
    TelegramContactDTO,
    TelegramContactMessageDTO,
    TelegramContactMessagesPageDTO,
    TelegramContactsPageDTO,
    TelegramDialogDTO,
    TelegramDialogSettingsDTO,
    TelegramDialogSettingsPayload,
    TelegramDialogsImportDTO,
    TelegramDialogsImportPayload,
    TelegramDialogsPageDTO,
    TelegramDialogsRemoveAddedDTO,
    TelegramDialogsRemoveAddedPayload,
    XFilesContractMetricsDTO,
    XFilesContractTemplateDTO,
    XFilesContractTemplatesPageDTO,
    XFilesDailyContactDTO,
    XFilesDailyContactsDTO,
    XFilesDailyPlanBucketDTO,
    XFilesDashboardInsightDTO,
    XFilesDealActionDTO,
    XFilesDealAssistantDTO,
    XFilesDealAuditDTO,
    XFilesDealAuditPageDTO,
    XFilesDealContractKitDTO,
    XFilesDealContractStatusPayload,
    XFilesDealConversionDTO,
    XFilesDealDTO,
    XFilesDealOpportunitiesDTO,
    XFilesDealOpportunityDTO,
    XFilesDealPatchPayload,
    XFilesDealPayload,
    XFilesDealReminderDTO,
    XFilesDealRemindersDTO,
    XFilesDealsKanbanColumnDTO,
    XFilesDealsKanbanDTO,
    XFilesDealsPageDTO,
    XFilesDealsStatusDTO,
    XFilesEventSalesPlanDTO,
    XFilesEventSalesPlanItemDTO,
    XFilesEventSalesWindowDTO,
    XFilesFunctionImpactDTO,
    XFilesFunnelStepDTO,
    XFilesLicenseActionDTO,
    XFilesLicenseActivatePayload,
    XFilesLicenseAuditDTO,
    XFilesLicenseEmailImportDTO,
    XFilesLicenseMenuCheckDTO,
    XFilesLicenseMenuCheckPayload,
    XFilesLicenseMenuItemDTO,
    XFilesLicenseMenusDTO,
    XFilesLicenseStatusDTO,
    XFilesMetricHistoryPointDTO,
    XFilesNeedSignalDTO,
    XFilesNeedSignalsPageDTO,
    XFilesNegotiationBriefDTO,
    XFilesNorthStarDTO,
    XFilesOutreachReplyRateDTO,
    XFilesOutreachSequenceActionDTO,
    XFilesOutreachSequenceDTO,
    XFilesOutreachSequencePatchPayload,
    XFilesOutreachSequencePayload,
    XFilesOutreachSequencesPageDTO,
    XFilesOutreachStatsDTO,
    XFilesOutreachTouchDTO,
    XFilesOutreachTouchStatusPayload,
    XFilesProductMarginDTO,
    XFilesProductMarginPayload,
    XFilesProductMarginsPageDTO,
    XFilesProfitOptimizationDTO,
    XFilesRouteMeetingDayDTO,
    XFilesTemplateModelBenchmarkDTO,
)


DB: Dict[str, Lead] = {}

# Seed
seed1 = Lead(
    name="Иван Петров", title="CTO", phone="+7 999 123-45-67", email="ivan@example.com",
    score=72, tags=["горячий"], company="ООО Рога", source="VK", activity="active",
    stage="Квалификация",
    lastAt=datetime.now().strftime("%Y-%m-%d %H:%M"),
    profile=Profile(topics=["DevOps","CI/CD"], risks=["сроки"], nextStep="Назначить демо"),
    deal=Deal(product="AI Code Review", potential=1500000, budget=800000, stage="Квалификация", probability=35),
    messages=[
        {"id": str(uuid4()), "from":"lead", "text":"Привет! Интересует аудит кода.", "when":"вчера", "channel":"TG"},
        {"id": str(uuid4()), "from":"me", "text":"Готовы показать демо завтра", "when":"вчера", "channel":"TG"},
    ],
)
seed2 = Lead(
    name="Anna Smith", title="Head of Ops", phone="+44 7777 000111", email="anna@smith.co.uk",
    score=40, tags=["теплый"], company="Smith Ltd", source="Telegram", activity="idle",
    stage="Новый",
    lastAt=datetime.now().strftime("%Y-%m-%d %H:%M"),
    profile=Profile(topics=["Automation"], risks=[], nextStep="Собрать требования"),
    deal=Deal(product="Process Mining", potential=900000, budget=0, stage="Новый", probability=10),
    messages=[
        {"id": str(uuid4()), "from":"lead", "text":"We need automation ideas.", "when":"today", "channel":"TG"},
    ],
)

for s in (seed1, seed2):
    DB[s.id] = s









# Простая "псевдо-БД" в памяти (замените на свою)
DBmessages = {"messages": []}

# Эндпоинт приёма сообщений

























































































































































































OutreachTouchStatus = Literal[
    "draft",
    "approved",
    "sent",
    "replied",
    "meeting_booked",
    "no_reply",
    "do_not_contact",
]




















DealStage = Literal[
    "idea",
    "lead",
    "qualified",
    "proposal",
    "negotiation",
    "contract",
    "won",
    "lost",
]

_XFILES_STAGE_ORDER: List[str] = ["idea", "lead", "qualified", "proposal", "negotiation", "contract", "won", "lost"]
_XFILES_STAGE_LABELS: Dict[str, str] = {
    "idea": "Идеи",
    "lead": "Лиды",
    "qualified": "Квалифицированы",
    "proposal": "КП",
    "negotiation": "Переговоры",
    "contract": "Договор",
    "won": "Выиграны",
    "lost": "Потеряны",
}


def _xfiles_clear_deal_api_caches(schedule_warmup: bool = True) -> None:
    for prefix in (
        "xfiles_deals_status",
        "xfiles_deals:",
        "xfiles_deals_kanban:",
        "xfiles_deals_audit:",
        "xfiles_deal_reminders:",
        "xfiles_deal_conversion",
        "xfiles_profit_optimization",
        "xfiles_deal_opportunities:",
        "xfiles_north_star",
        "xfiles_contract_templates",
        "xfiles_contract_metrics",
        "xfiles_deal_assistant:",
        "xfiles_deal_contract_kit:",
        "xfiles_deal_negotiation_brief:",
        "xfiles_daily_contacts:",
        "xfiles_event_sales_plan:",
        "dashboard_summary:",
    ):
        _api_snapshot_cache_clear_prefix(prefix)
    scheduler = globals().get("_xfiles_schedule_deal_cache_warmup")
    if schedule_warmup and callable(scheduler):
        scheduler("mutation")




















XFilesContractStatus = Literal["needs_data", "proposal_ready", "sent", "negotiation", "signed", "paid"]
XFilesContractTemplateKind = Literal["proposal", "contract", "invoice", "appendix", "nda"]























































































def _ensure_dir_exists():
    if not PAYME_OUT_DIR.exists():
        try:
            PAYME_OUT_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PAYME_OUT_DIR cannot be created: {PAYME_OUT_DIR}: {exc}") from exc
    _sync_legacy_payme_outputs()


def _ensure_cache_dir_exists() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


from app.workers.analysis_cache import (
    _analysis_cache_path,
    _analysis_rows,
    _analysis_state,
    _build_analysis_status,
    _load_analysis_cache_rows_limited,
    _refresh_contacts_cache_sync,
    _refresh_crm_cache_sync,
    _refresh_event_cache_sync,
    _refresh_routes_cache_sync,
    _schedule_analysis_refresh,
)



def _analysis_state_root() -> Dict[str, Any]:
    root = telegram_sync.state.get("_analysis_cache")
    if not isinstance(root, dict):
        root = {}
        telegram_sync.state["_analysis_cache"] = root
    return root




def _analysis_progress_log(kind: AnalysisKind, message: str) -> None:
    state = _analysis_state(kind)
    timestamp = _utc_now().strftime("%Y-%m-%d %H:%M:%S")
    current_log = state.get("progress_log")
    if not isinstance(current_log, list):
        current_log = []
    current_log = [f"{timestamp} {str(message or '').strip()}"] + current_log[:19]
    state["progress_log"] = current_log


_ANALYSIS_PROGRESS_UNSET = object()


def _analysis_set_progress(
    kind: AnalysisKind,
    *,
    current: Optional[int] = None,
    total: Optional[int] = None,
    label: Optional[str] = None,
    current_item: Any = _ANALYSIS_PROGRESS_UNSET,
    started_at: Optional[str] = None,
    append_log: Optional[str] = None,
    save: bool = True,
) -> None:
    state = _analysis_state(kind)
    if current is not None:
        state["progress_current"] = max(0, int(current))
    if total is not None:
        state["progress_total"] = max(0, int(total))
    total_value = int(state.get("progress_total") or 0)
    current_value = int(state.get("progress_current") or 0)
    state["progress_percent"] = 0.0 if total_value <= 0 else round(max(0.0, min(100.0, (current_value / total_value) * 100.0)), 2)
    if label is not None:
        state["progress_label"] = label
    if current_item is not _ANALYSIS_PROGRESS_UNSET:
        state["current_item"] = current_item
    if started_at is not None:
        state["progress_started_at"] = started_at
    if append_log:
        _analysis_progress_log(kind, append_log)
    if save:
        telegram_sync.save_state()


def _load_analysis_cache_rows(kind: AnalysisKind) -> List[Dict[str, Any]]:
    path = _analysis_cache_path(kind)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _analysis_cache_has_rows(kind: AnalysisKind) -> bool:
    path = _analysis_cache_path(kind)
    if not path.exists():
        return False
    try:
        if path.stat().st_size <= 2:
            return False
        with path.open("r", encoding="utf-8", errors="replace") as file:
            head = file.read(2048)
    except OSError:
        return False
    return any(ch not in "[] \n\r\t," for ch in head)




def _save_analysis_cache_rows(kind: AnalysisKind, rows: List[Dict[str, Any]]) -> None:
    path = _analysis_cache_path(kind)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False)
    tmp.replace(path)


def _clear_analysis_cache_rows_file(kind: AnalysisKind) -> None:
    path = _analysis_cache_path(kind)
    path.unlink(missing_ok=True)


def _clear_contacts_messages_cache_file() -> None:
    _contacts_messages_cache_path().unlink(missing_ok=True)


def _iter_jsonl_from_offset(path: Path, offset: int = 0):
    with path.open("r", encoding="utf-8", errors="replace") as file:
        file.seek(max(offset, 0))
        while True:
            line = file.readline()
            if not line:
                break
            try:
                record = json.loads(line)
            except Exception:
                continue
            if isinstance(record, dict):
                yield record


def _keywords_hash(keywords: List[str]) -> str:
    payload = "\n".join(sorted(str(item or "").strip().lower() for item in keywords if str(item or "").strip()))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _analysis_next_refresh_at(kind: AnalysisKind) -> Optional[str]:
    state = _analysis_state(kind)
    last_refresh = state.get("last_refresh_at")
    if not last_refresh:
        return None
    try:
        last_dt = datetime.fromisoformat(str(last_refresh))
    except Exception:
        return None
    interval_sec = int(state.get("interval_sec") or _ANALYSIS_AUTO_REFRESH_DEFAULT_SEC)
    return (last_dt + timedelta(seconds=interval_sec)).isoformat()




def _analysis_cache_ready_fast(kind: AnalysisKind) -> bool:
    state = _analysis_state(kind)
    if kind == "contacts" and _duckdb_contacts_ready():
        return True
    if kind == "crm" and _duckdb_crm_ready():
        return True
    if kind == "events" and _duckdb_events_ready():
        return True
    if int(state.get("total_rows", 0) or 0) > 0:
        return True
    return _analysis_cache_path(kind).exists()


def _dashboard_analysis_preview_rows(kind: AnalysisKind, limit: int) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 1), 50))
    if kind == "contacts":
        if _duckdb_contacts_ready():
            return _duckdb_load_contact_rows(limit=safe_limit)
        return []
    if kind == "crm":
        if _duckdb_crm_ready():
            return _duckdb_load_crm_rows(limit=safe_limit)
        return []
    if kind == "events":
        if _duckdb_events_ready():
            return _duckdb_load_event_rows(limit=safe_limit)
        return []
    return []


def _analysis_due(kind: AnalysisKind) -> bool:
    state = _analysis_state(kind)
    if not bool(state.get("enabled", True)) or bool(state.get("running", False)):
        return False
    if kind == "events":
        current_hash = _keywords_hash(_get_event_keywords())
        if state.get("last_keywords_hash") == "__stale__":
            return True
        if state.get("last_keywords_hash") not in (None, current_hash):
            return True
    if not _analysis_cache_has_rows(kind):
        duckdb_ready_from_state = (
            (kind == "contacts" and _duckdb_contacts_ready())
            or (kind in {"crm", "events"} and bool(state.get("duckdb_ready")))
        )
        if not duckdb_ready_from_state:
            return True
    last_refresh = state.get("last_refresh_at")
    if not last_refresh:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last_refresh))
    except Exception:
        return True
    interval_sec = int(state.get("interval_sec") or _ANALYSIS_AUTO_REFRESH_DEFAULT_SEC)
    return (_utc_now() - last_dt).total_seconds() >= interval_sec


def _paginate_items(items: List[Any], page: int, page_size: int) -> Dict[str, Any]:
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, int(page_size or 1))
    total = len(items)
    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    safe_page = min(safe_page, total_pages)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return {
        "items": items[start:end],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
    }


def _lead_matches_filters(
    lead: LeadDTO,
    query: str = "",
    show_channels: bool = True,
    show_groups: bool = True,
    show_private: bool = True,
    show_bots: bool = False,
    show_archived: bool = False,
    scan_filter: str = "all",
) -> bool:
    normalized_scan_filter = str(scan_filter or "all").strip().lower()
    scan_filter_needs_inactive = normalized_scan_filter in {"not_scanning", "has_db"}
    if lead.sync_status == "archived" and not show_archived and not scan_filter_needs_inactive:
        return False
    allowed_types = set()
    if show_channels:
        allowed_types.add("channel")
    if show_groups:
        allowed_types.add("group")
    if show_private:
        allowed_types.add("private")
    if show_bots:
        allowed_types.add("bot")
    # Sync/chat lists must still show an explicitly selected bot source, even
    # when the UI hides the generic "Bots" filter. Otherwise selected sources
    # such as faino_psy_bot disappear from Sync and chats while the worker still
    # has them in _source_selectors.
    if lead.chat_type not in allowed_types and not (lead.chat_type == "bot" and bool(lead.in_source)):
        return False
    if lead.is_archived and not show_archived:
        return False
    is_scanning = bool(lead.in_source and lead.source_scan_allowed)
    if normalized_scan_filter == "scanning" and not is_scanning:
        return False
    if normalized_scan_filter == "not_scanning" and is_scanning:
        return False
    if normalized_scan_filter == "has_db" and not (lead.has_jsonl or int(lead.count or 0) > 0):
        return False
    if not query:
        return True
    hay = " ".join(
        [
            lead.name,
            lead.file,
            lead.source_selector or "",
            lead.last_text_preview or "",
            lead.last_text_full or "",
        ]
    ).lower()
    return query in hay


def _sort_leads_for_view(items: List[LeadDTO], sort_mode: str = "recent") -> List[LeadDTO]:
    if sort_mode == "status":
        status_rank = {"active": 0, "pending": 1, "archived": 2}
        return sorted(
            items,
            key=lambda lead: (
                0 if lead.in_source else 1,
                status_rank.get(lead.sync_status, 9),
                -(lead.count or 0),
                -(1 if lead.last_date_utc else 0),
                lead.last_date_utc or "",
                lead.name.lower(),
            ),
        )

    return sorted(
        items,
        key=lambda lead: (
            1 if lead.last_date_utc else 0,
            lead.last_date_utc or "",
            int(lead.count or 0),
            lead.name.lower(),
        ),
        reverse=True,
    )


def _dialog_matches_filters(
    dialog: TelegramDialogDTO,
    query: str = "",
    show_channels: bool = True,
    show_groups: bool = True,
    show_private: bool = True,
    show_bots: bool = False,
    show_archived: bool = False,
    membership_filter: str = "all",
) -> bool:
    if dialog.chat_type == "channel" and not show_channels:
        return False
    if dialog.chat_type == "group" and not show_groups:
        return False
    if dialog.chat_type == "private" and not show_private:
        return False
    if dialog.chat_type == "bot" and not show_bots:
        return False
    if dialog.is_archived and not show_archived:
        return False
    if membership_filter == "added" and not dialog.is_already_added:
        return False
    if membership_filter == "not_added" and dialog.is_already_added:
        return False
    if not query:
        return True
    return any(
        query in str(value or "").lower()
        for value in [
            dialog.title,
            dialog.username and f"@{dialog.username}",
            dialog.selector,
            dialog.chat_type,
            dialog.last_text_preview,
            dialog.last_text_full,
        ]
    )


def _dialog_identity_values(dialog: TelegramDialogDTO) -> Set[str]:
    values = {
        _selector_identity(dialog.selector),
        _selector_identity(dialog.username or ""),
        _selector_identity(dialog.title or ""),
        _selector_identity(str(dialog.id or "")),
    }
    return {value for value in values if value}


def _effective_import_limits_from_cached_state(
    selector: Union[str, int],
    *,
    settings: Dict[str, Any],
    import_settings: Dict[str, Dict[str, int]],
    max_history: int,
    max_messages: int,
) -> Dict[str, int]:
    try:
        key = _selector_identity(str(selector))
    except Exception:
        key = str(selector or "").strip().lower()
    stored = import_settings.get(key, {})
    try:
        default_history = int(settings.get("import_default_history_months") or 1)
    except Exception:
        default_history = 1
    try:
        default_messages = int(settings.get("import_default_message_limit") or 1000)
    except Exception:
        default_messages = 1000
    try:
        history_months = int(stored.get("import_history_months") or default_history)
    except Exception:
        history_months = default_history
    try:
        message_limit = int(stored.get("import_message_limit") or default_messages)
    except Exception:
        message_limit = default_messages
    return {
        "import_history_months": 0 if max_history == 0 or history_months == 0 else max(1, min(max_history, history_months)),
        "import_message_limit": 0 if max_messages == 0 or message_limit == 0 else max(1, min(max_messages, message_limit)),
        "import_max_history_months": max_history,
        "import_max_message_limit": max_messages,
    }


def _source_selector_fallback_dialog(
    selector: str,
    *,
    import_limits: Optional[Dict[str, int]] = None,
) -> Optional[TelegramDialogDTO]:
    try:
        normalized = _normalize_source_selector(selector)
    except ValueError:
        return None
    clean = normalized.lstrip("@").strip()
    if not clean:
        return None
    limits = import_limits or _effective_import_limits_for_selector(normalized)
    digest = hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()
    synthetic_id = int(digest[:12], 16)
    chat_type = "group"
    waiting_text = "Добавлен в источники, ожидает обновления кэша Telegram."
    return TelegramDialogDTO(
        id=synthetic_id,
        title=clean,
        username=None if normalized.isdigit() else clean,
        selector=normalized,
        chat_type=chat_type,
        is_archived=False,
        is_already_added=True,
        unread_count=0,
        last_date_utc=None,
        last_text_preview=waiting_text,
        last_text_full=waiting_text,
        **limits,
    )


def _merge_added_source_selectors_into_dialogs(dialogs: List[TelegramDialogDTO]) -> List[TelegramDialogDTO]:
    result = list(dialogs)
    raw_selectors = _source_selectors_as_strings()
    selector_by_identity: Dict[str, str] = {}
    for raw_selector in raw_selectors:
        identity = _selector_identity(raw_selector)
        if not identity:
            continue
        selector_by_identity.setdefault(identity, str(raw_selector))
    source_identities = set(selector_by_identity.keys())
    known: Set[str] = set()
    for dialog in result:
        dialog_identities = _dialog_identity_values(dialog)
        dialog.is_already_added = bool(dialog_identities.intersection(source_identities))
        known.update(dialog_identities)
    settings = _get_app_settings()
    max_history = _xfiles_import_history_months_max()
    max_messages = _xfiles_import_message_limit_max()
    import_settings = _import_dialog_settings_state()
    for selector in source_identities:
        identity = _selector_identity(selector)
        if not identity or identity in known:
            continue
        raw_selector = selector_by_identity.get(identity, selector)
        limits = _effective_import_limits_from_cached_state(
            raw_selector,
            settings=settings,
            import_settings=import_settings,
            max_history=max_history,
            max_messages=max_messages,
        )
        fallback = _source_selector_fallback_dialog(raw_selector, import_limits=limits)
        if fallback is not None:
            result.append(fallback)
            known.update(_dialog_identity_values(fallback))
    return result


def _filter_image_assets(
    items: List[ImageAssetDTO],
    query: str = "",
    lead_filter: str = "",
    recognized_only: bool = False,
    pending_only: bool = False,
) -> List[ImageAssetDTO]:
    result: List[ImageAssetDTO] = []
    for row in items:
        if recognized_only and not row.recognized:
            continue
        if pending_only and row.recognized:
            continue
        if lead_filter:
            lead_hay = f"{row.lead} {row.file_name}".lower()
            if lead_filter not in lead_hay:
                continue
        if query:
            hay = " ".join(
                [
                    row.lead,
                    row.file_name,
                    row.ocr_preview or "",
                ]
            ).lower()
            if query not in hay:
                continue
        result.append(row)
    return result


def _filter_event_messages(
    items: List[EventMessageDTO],
    query: str = "",
    lead_filter: str = "",
    sender_filter: str = "",
    keyword_filter: str = "",
    date_from: str = "",
    date_to: str = "",
) -> List[EventMessageDTO]:
    result: List[EventMessageDTO] = []
    for row in items:
        if query:
            hay = " ".join(
                [
                    row.lead,
                    row.source_selector or "",
                    row.text,
                    " ".join(row.matched_keywords),
                    row.sender_username or "",
                    row.sender_name or "",
                ]
            ).lower()
            if query not in hay:
                continue
        if lead_filter:
            lead_hay = f"{row.lead} {row.source_selector or ''}".lower()
            if lead_filter not in lead_hay:
                continue
        if sender_filter:
            sender_hay = f"{row.sender_username or ''} {row.sender_name or ''}".lower()
            if sender_filter not in sender_hay:
                continue
        if keyword_filter:
            row_keywords = [str(item or "").lower() for item in row.matched_keywords]
            if not any(keyword_filter in item for item in row_keywords):
                continue
        row_date = str(row.date_utc or "")[:10]
        if date_from and row_date and row_date < date_from:
            continue
        if date_to and row_date and row_date > date_to:
            continue
        result.append(row)
    return result


def _filter_crm_contacts(
    items: List[CrmContactDTO],
    query: str = "",
    lead_filter: str = "",
    only_name: bool = False,
    only_phone: bool = False,
    only_email: bool = False,
    only_company: bool = False,
    only_city: bool = False,
    only_title: bool = False,
) -> List[CrmContactDTO]:
    result: List[CrmContactDTO] = []
    for row in items:
        if only_name and not row.name_components_count:
            continue
        if only_phone and not row.phones:
            continue
        if only_email and not row.emails:
            continue
        if only_company and not row.companies:
            continue
        if only_city and not row.city:
            continue
        if only_title and not row.job_title:
            continue
        if lead_filter:
            lead_hay = f"{row.lead} {row.source_selector or ''}".lower()
            if lead_filter not in lead_hay:
                continue
        if query:
            hay = " ".join(
                [
                    row.lead,
                    row.source_selector or "",
                    row.sender_username or "",
                    row.sender_name or "",
                    row.full_name or "",
                    row.first_name or "",
                    row.last_name or "",
                    row.patronymic or "",
                    row.job_title or "",
                    " ".join(row.companies),
                    " ".join(row.phones),
                    " ".join(row.emails),
                    row.city or "",
                    row.text or "",
                ]
            ).lower()
            if query not in hay:
                continue
        result.append(row)
    return result


_OUTREACH_FIELD_LABELS: Dict[str, str] = {
    "fio": "ФИО",
    "job_title": "Должность",
    "company": "Компании",
    "contact": "Контакты",
    "city": "Город",
    "message": "Сообщение",
    "event_message": "Мероприятие",
    "chat": "Чат",
    "media": "Media",
    "telegram_contact": "Контакт",
    "import_dialog": "Import",
    "jur_entity": "ЮР.ЛИЦА.",
}


def _normalize_outreach_field_type(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    aliases = {
        "name": "fio",
        "full_name": "fio",
        "phone": "contact",
        "email": "contact",
        "contacts": "contact",
        "title": "job_title",
        "position": "job_title",
        "companies": "company",
        "text": "message",
        "message_text": "message",
        "event": "event_message",
        "event_messages": "event_message",
        "events": "event_message",
        "lead": "chat",
        "dialog": "import_dialog",
        "telegram_dialog": "import_dialog",
        "contact_author": "telegram_contact",
        "author": "telegram_contact",
        "jur": "jur_entity",
        "jur_entities": "jur_entity",
        "ur_entity": "jur_entity",
        "ur_entities": "jur_entity",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in _OUTREACH_FIELD_LABELS:
        normalized = "message"
    return normalized


def _outreach_field_label(field_type: str, custom_label: Optional[str] = None) -> str:
    custom = str(custom_label or "").strip()
    if custom:
        return custom
    return _OUTREACH_FIELD_LABELS.get(_normalize_outreach_field_type(field_type), "Контакты")


_OUTREACH_MESSAGE_FIELD_TYPES = {"message", "event_message"}
_OUTREACH_CONTEXT_MESSAGE_FIELD_TYPES = {
    "chat",
    "import_dialog",
    "telegram_contact",
    "jur_entity",
    "media",
}


def _outreach_compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _outreach_source_terms(lead: Optional[str], source_selector: Optional[str]) -> List[str]:
    terms: List[str] = []
    seen: set[str] = set()
    for raw in [lead, source_selector]:
        value = str(raw or "").strip()
        if not value:
            continue
        candidates = [value, value.lstrip("@")]
        for candidate in candidates:
            normalized = candidate.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(normalized)
    return terms


def _outreach_source_sql_clause(terms: List[str]) -> tuple[str, List[Any]]:
    if not terms:
        return "", []
    clauses: List[str] = []
    params: List[Any] = []
    for term in terms:
        clauses.append(
            "("
            "lower(coalesce(chat_username, '')) = ? OR "
            "lower(coalesce(source_key, '')) = ? OR "
            "lower(coalesce(source_jsonl, '')) LIKE ? OR "
            "lower(coalesce(source_jsonl, '')) LIKE ? OR "
            "lower(coalesce(chat_title, '')) = ?"
            ")"
        )
        params.extend([term, term, f"%/{term}.jsonl", f"%{term}.jsonl", term])
    return "(" + " OR ".join(clauses) + ")", params


def _outreach_fetch_full_message_text_sync(
    lead: Optional[str],
    source_selector: Optional[str],
    message_id: Optional[int],
    date_utc: Optional[str],
    current_text: Optional[str],
) -> Optional[str]:
    if duckdb is None or not DUCKDB_PATH.exists():
        return None

    terms = _outreach_source_terms(lead, source_selector)
    source_clause, source_params = _outreach_source_sql_clause(terms)

    def fetch_one(where_parts: List[str], params: List[Any]) -> Optional[str]:
        sql = """
            SELECT text
            FROM messages_raw
            WHERE length(trim(coalesce(text, ''))) > 0
        """
        if where_parts:
            sql += " AND " + " AND ".join(f"({part})" for part in where_parts)
        sql += """
            ORDER BY
                coalesce(date_utc_raw, '') DESC,
                source_offset DESC
            LIMIT 1
        """
        conn = _duckdb_connect()
        try:
            row = conn.execute(sql, params).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        text = str(row[0] or "").strip()
        return text or None

    try:
        message_id_int = int(message_id) if message_id is not None else None
    except Exception:
        message_id_int = None

    if message_id_int is not None:
        parts = ["message_id = ?"]
        params: List[Any] = [message_id_int]
        if source_clause:
            parts.append(source_clause)
            params.extend(source_params)
        result = fetch_one(parts, params)
        if result:
            return result

    date_value = str(date_utc or "").strip()
    if date_value:
        date_prefix = date_value[:19]
        parts = [
            "(date_utc_raw = ? OR substr(date_utc_raw, 1, 19) = ? OR substr(CAST(date_utc AS VARCHAR), 1, 19) = ?)"
        ]
        params = [date_value, date_prefix, date_prefix]
        if source_clause:
            parts.append(source_clause)
            params.extend(source_params)
        result = fetch_one(parts, params)
        if result:
            return result

    compact_current = _outreach_compact_text(current_text).rstrip(".…")
    if len(compact_current) >= 16:
        needle = compact_current[:96].lower()
        parts = ["lower(coalesce(text, '')) LIKE ?"]
        params = [f"%{needle}%"]
        if source_clause:
            parts.append(source_clause)
            params.extend(source_params)
        result = fetch_one(parts, params)
        if result:
            return result

    return None


def _outreach_full_text_candidate(
    lead: Optional[str],
    source_selector: Optional[str],
    message_id: Optional[int],
    date_utc: Optional[str],
    value: Optional[str],
    text: Optional[str],
) -> Optional[str]:
    resolved = _outreach_fetch_full_message_text_sync(
        lead=lead,
        source_selector=source_selector,
        message_id=message_id,
        date_utc=date_utc,
        current_text=text or value,
    )
    candidates = [
        str(resolved or "").strip(),
        str(text or "").strip(),
    ]
    candidates = [item for item in candidates if item]
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(_outreach_compact_text(item)))


def _outreach_expand_value_with_full_text(field_type: str, value: str, text: str, full_text: Optional[str]) -> str:
    current_value = str(value or "").strip()
    full = str(full_text or "").strip()
    if not full:
        return current_value

    current_compact = _outreach_compact_text(current_value)
    text_compact = _outreach_compact_text(text)
    full_compact = _outreach_compact_text(full)
    if len(full_compact) <= len(current_compact):
        return current_value

    if field_type in _OUTREACH_MESSAGE_FIELD_TYPES:
        return full

    if field_type in _OUTREACH_CONTEXT_MESSAGE_FIELD_TYPES:
        if text_compact and text_compact in current_compact and ": " in current_value:
            prefix = current_value.split(": ", 1)[0].strip()
            return f"{prefix}: {full}" if prefix else full
        if current_compact == text_compact:
            return full

    return current_value


def _outreach_item_id(payload: Dict[str, Any]) -> str:
    field_type = _normalize_outreach_field_type(str(payload.get("field_type") or ""))
    basis = {
        "field_type": field_type,
        "lead": payload.get("lead"),
        "message_id": payload.get("message_id"),
        "date_utc": payload.get("date_utc"),
    }
    if not (field_type in _OUTREACH_MESSAGE_FIELD_TYPES and (payload.get("message_id") or payload.get("date_utc"))):
        basis["value"] = payload.get("value")
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _outreach_item_from_payload(payload: OutreachCrmFieldPayload) -> OutreachCrmFieldDTO:
    field_type = _normalize_outreach_field_type(payload.field_type)
    raw_value = str(payload.value or "").strip()
    raw_text = str(payload.text or "").strip()
    full_text = _outreach_full_text_candidate(
        lead=payload.lead,
        source_selector=payload.source_selector,
        message_id=payload.message_id,
        date_utc=payload.date_utc,
        value=raw_value,
        text=raw_text,
    ) if field_type in _OUTREACH_MESSAGE_FIELD_TYPES | _OUTREACH_CONTEXT_MESSAGE_FIELD_TYPES else raw_text or None
    value = _outreach_expand_value_with_full_text(field_type, raw_value, raw_text, full_text)
    if not value:
        raise HTTPException(status_code=400, detail="Outreach value is required")
    data = {
        "field_type": field_type,
        "field_label": _outreach_field_label(field_type, payload.field_label),
        "value": value,
        "contact_key": str(payload.contact_key or "").strip() or None,
        "lead": str(payload.lead or "").strip() or None,
        "source_selector": str(payload.source_selector or "").strip() or None,
        "message_id": int(payload.message_id) if payload.message_id is not None else None,
        "date_utc": str(payload.date_utc or "").strip() or None,
        "text": (full_text or raw_text) or None,
        "sender_username": str(payload.sender_username or "").strip() or None,
        "sender_name": str(payload.sender_name or "").strip() or None,
    }
    return OutreachCrmFieldDTO(
        id=_outreach_item_id(data),
        status="new",
        created_at=_utc_now().isoformat(),
        **data,
    )


def _outreach_row_to_dto(row: Any) -> OutreachCrmFieldDTO:
    return OutreachCrmFieldDTO(
        id=str(row[0] or ""),
        field_type=str(row[1] or ""),
        field_label=str(row[2] or "") or _outreach_field_label(str(row[1] or "")),
        value=str(row[3] or ""),
        contact_key=str(row[4] or "") or None,
        lead=str(row[5] or "") or None,
        source_selector=str(row[6] or "") or None,
        message_id=_duckdb_optional_int(row[7]),
        date_utc=str(row[8] or "") or None,
        text=str(row[9] or "") or None,
        sender_username=str(row[10] or "") or None,
        sender_name=str(row[11] or "") or None,
        status=str(row[12] or "") or "new",
        created_at=str(row[13] or ""),
    )


def _outreach_state_fallback() -> Dict[str, Any]:
    current = telegram_sync.state.get("_outreach")
    if not isinstance(current, dict):
        current = {}
    items = current.get("crm_fields")
    if not isinstance(items, list):
        items = []
    current["crm_fields"] = items
    telegram_sync.state["_outreach"] = current
    return current


def _outreach_fallback_items() -> List[OutreachCrmFieldDTO]:
    items: List[OutreachCrmFieldDTO] = []
    for raw in _outreach_state_fallback().get("crm_fields") or []:
        if not isinstance(raw, dict):
            continue
        try:
            items.append(OutreachCrmFieldDTO(**raw))
        except Exception:
            continue
    return items


def _upsert_outreach_item(item: OutreachCrmFieldDTO) -> OutreachCrmFieldDTO:
    if duckdb is not None:
        _duckdb_init_schema_sync()
        conn = _duckdb_connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO outreach_crm_fields (
                    item_id, field_type, field_label, value, contact_key, lead, source_selector,
                    message_id, date_utc_raw, text, sender_username, sender_name,
                    status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    item.id,
                    item.field_type,
                    item.field_label,
                    item.value,
                    item.contact_key,
                    item.lead,
                    item.source_selector,
                    item.message_id,
                    item.date_utc,
                    item.text,
                    item.sender_username,
                    item.sender_name,
                    item.status,
                    item.created_at,
                ],
            )
        finally:
            conn.close()
        return item

    state = _outreach_state_fallback()
    rows = [row for row in state.get("crm_fields") or [] if row.get("id") != item.id]
    rows.insert(0, item.model_dump())
    state["crm_fields"] = rows
    telegram_sync.save_state()
    return item


def _delete_outreach_item(item_id: str) -> bool:
    target = str(item_id or "").strip()
    if not target:
        return False
    if duckdb is not None:
        _duckdb_init_schema_sync()
        conn = _duckdb_connect()
        try:
            before = conn.execute(
                "SELECT COUNT(*) FROM outreach_crm_fields WHERE item_id = ?",
                [target],
            ).fetchone()
            conn.execute("DELETE FROM outreach_crm_fields WHERE item_id = ?", [target])
            return bool(int(before[0] or 0) > 0)
        finally:
            conn.close()

    state = _outreach_state_fallback()
    rows = [row for row in state.get("crm_fields") or [] if row.get("id") != target]
    changed = len(rows) != len(state.get("crm_fields") or [])
    state["crm_fields"] = rows
    if changed:
        telegram_sync.save_state()
    return changed


def _outreach_contact_aliases(contact_key: str, contact: Optional[Dict[str, Any]] = None) -> Dict[str, set[str]]:
    contact_data = contact or {}

    def norm(value: Any) -> str:
        text = str(value or "").strip().lower()
        return text.lstrip("@")

    keys = {norm(contact_key)}
    usernames: set[str] = set()
    names: set[str] = set()
    values = {norm(contact_key)}
    for raw in [
        contact_data.get("contact_key"),
        contact_data.get("display_name"),
        contact_data.get("sender_name"),
        contact_data.get("sender_username"),
    ]:
        normalized = norm(raw)
        if normalized:
            values.add(normalized)
    username = norm(contact_data.get("sender_username"))
    if username:
        usernames.add(username)
        values.add(username)
    name = norm(contact_data.get("sender_name") or contact_data.get("display_name"))
    if name:
        names.add(name)
        values.add(name)
    return {
        "keys": {item for item in keys if item},
        "usernames": {item for item in usernames if item},
        "names": {item for item in names if item},
        "values": {item for item in values if item},
    }


def _outreach_item_matches_contact(
    item: OutreachCrmFieldDTO,
    contact_key: str,
    contact: Optional[Dict[str, Any]] = None,
) -> bool:
    aliases = _outreach_contact_aliases(contact_key, contact)

    def norm(value: Any) -> str:
        return str(value or "").strip().lower().lstrip("@")

    if norm(item.contact_key) in aliases["keys"]:
        return True
    if item.sender_username and norm(item.sender_username) in aliases["usernames"]:
        return True
    if item.sender_name and norm(item.sender_name) in aliases["names"]:
        return True
    if item.field_type == "telegram_contact" and norm(item.value) in aliases["values"]:
        return True
    return False


def _delete_outreach_items_for_contact(contact_key: str, contact: Optional[Dict[str, Any]] = None) -> int:
    target = str(contact_key or "").strip()
    if not target:
        return 0
    aliases = _outreach_contact_aliases(target, contact)
    keys = sorted(aliases["keys"])
    usernames = sorted(aliases["usernames"])
    names = sorted(aliases["names"])
    values = sorted(aliases["values"])
    if duckdb is not None:
        _duckdb_init_schema_sync()
        clauses: List[str] = []
        params: List[Any] = []
        if keys:
            placeholders = ", ".join(["?"] * len(keys))
            clauses.append(f"LOWER(COALESCE(contact_key, '')) IN ({placeholders})")
            params.extend(keys)
        if usernames:
            placeholders = ", ".join(["?"] * len(usernames))
            clauses.append(f"LOWER(REPLACE(COALESCE(sender_username, ''), '@', '')) IN ({placeholders})")
            params.extend(usernames)
        if names:
            placeholders = ", ".join(["?"] * len(names))
            clauses.append(f"LOWER(COALESCE(sender_name, '')) IN ({placeholders})")
            params.extend(names)
        if values:
            placeholders = ", ".join(["?"] * len(values))
            clauses.append(f"(field_type = 'telegram_contact' AND LOWER(COALESCE(value, '')) IN ({placeholders}))")
            params.extend(values)
        if not clauses:
            return 0
        where_sql = " OR ".join(f"({clause})" for clause in clauses)
        conn = _duckdb_connect()
        try:
            before = conn.execute(f"SELECT COUNT(*) FROM outreach_crm_fields WHERE {where_sql}", params).fetchone()
            conn.execute(f"DELETE FROM outreach_crm_fields WHERE {where_sql}", params)
            return int(before[0] or 0) if before else 0
        finally:
            conn.close()

    state = _outreach_state_fallback()
    keep: List[Dict[str, Any]] = []
    removed = 0
    for raw in state.get("crm_fields") or []:
        if not isinstance(raw, dict):
            continue
        try:
            item = OutreachCrmFieldDTO(**raw)
        except Exception:
            keep.append(raw)
            continue
        if _outreach_item_matches_contact(item, target, contact):
            removed += 1
            continue
        keep.append(raw)
    state["crm_fields"] = keep
    if removed:
        telegram_sync.save_state()
    return removed


def _load_outreach_items(
    query: str = "",
    field_type: str = "",
    limit: int = 5000,
) -> List[OutreachCrmFieldDTO]:
    normalized_field = _normalize_outreach_field_type(field_type) if field_type and field_type != "all" else ""
    if duckdb is not None:
        _duckdb_init_schema_sync()
        conn = _duckdb_connect()
        try:
            raw_rows = conn.execute(
                """
                SELECT
                    item_id, field_type, field_label, value, contact_key, lead, source_selector,
                    message_id, date_utc_raw, text, sender_username, sender_name,
                    status, CAST(created_at AS VARCHAR) AS created_at_raw
                FROM outreach_crm_fields
                ORDER BY created_at_raw DESC, date_utc_raw DESC
                LIMIT ?
                """,
                [max(1, int(limit or 1))],
            ).fetchall()
        finally:
            conn.close()
        items = [_outreach_row_to_dto(row) for row in raw_rows]
    else:
        items = _outreach_fallback_items()

    result: List[OutreachCrmFieldDTO] = []
    query_value = str(query or "").strip().lower()
    for item in items:
        if normalized_field and item.field_type != normalized_field:
            continue
        if query_value:
            hay = " ".join(
                [
                    item.field_label,
                    item.value,
                    item.contact_key or "",
                    item.lead or "",
                    item.source_selector or "",
                    item.sender_username or "",
                    item.sender_name or "",
                    item.text or "",
                ]
            ).lower()
            if query_value not in hay:
                continue
        result.append(item)
    return _xfiles_attach_deals_to_outreach_items(result)


from app.services.deals_runtime import *  # compatibility facade

from app.services.contact_llm_runtime import *  # compatibility facade

from app.services.telegram_sources_runtime import *  # compatibility facade

def _crm_compact_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _crm_title_case(value: str) -> str:
    parts = [part.strip() for part in re.split(r"\s+", value) if part.strip()]
    normalized: List[str] = []
    for part in parts:
        if "-" in part:
            normalized.append("-".join(chunk[:1].upper() + chunk[1:].lower() for chunk in part.split("-") if chunk))
        else:
            normalized.append(part[:1].upper() + part[1:].lower())
    return " ".join(normalized)


def _crm_is_patronymic(token: str) -> bool:
    lowered = str(token or "").strip().lower()
    return bool(lowered) and any(lowered.endswith(suffix) for suffix in _CRM_PATRONYMIC_SUFFIXES)


def _crm_looks_like_first_name(token: str) -> bool:
    lowered = str(token or "").strip().lower()
    return lowered in _CRM_COMMON_FIRST_NAMES


def _crm_looks_like_surname(token: str) -> bool:
    lowered = str(token or "").strip().lower()
    if not lowered:
        return False
    if lowered in _CRM_COMMON_FIRST_NAMES:
        return False
    return any(lowered.endswith(suffix) for suffix in _CRM_SURNAME_SUFFIXES)


def _crm_parse_name_tokens(tokens: List[str]) -> Optional[Dict[str, Any]]:
    cleaned = [_crm_title_case(token) for token in tokens if token]
    if not cleaned:
        return None
    if any(token.lower() in _CRM_NAME_STOPWORDS for token in cleaned):
        return None

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    patronymic: Optional[str] = None

    if len(cleaned) >= 3:
        a, b, c = cleaned[:3]
        if _crm_is_patronymic(c):
            patronymic = c
            if _crm_looks_like_surname(a) and not _crm_looks_like_surname(b):
                last_name = a
                first_name = b
            else:
                first_name = a
                last_name = b
        elif _crm_is_patronymic(b):
            first_name = a
            patronymic = b
            last_name = c
        else:
            if _crm_looks_like_surname(a) and not _crm_looks_like_surname(b):
                last_name = a
                first_name = b
                patronymic = c
            else:
                first_name = a
                last_name = b
                patronymic = c
    elif len(cleaned) == 2:
        a, b = cleaned
        if _crm_looks_like_surname(a) and not _crm_looks_like_surname(b):
            last_name = a
            first_name = b
        else:
            first_name = a
            last_name = b
    else:
        token = cleaned[0]
        if _crm_is_patronymic(token):
            patronymic = token
        elif _crm_looks_like_surname(token):
            last_name = token
        else:
            first_name = token

    parts = [item for item in (last_name, first_name, patronymic) if item]
    full_name = " ".join(parts) if parts else None
    components = sum(1 for item in (first_name, last_name, patronymic) if item)
    if not full_name or components <= 0:
        return None

    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "patronymic": patronymic,
        "name_components_count": components,
    }


def _crm_score_name_tokens(tokens: List[str]) -> int:
    score = len(tokens)
    if any(_crm_looks_like_first_name(token) for token in tokens):
        score += 2
    if any(_crm_looks_like_surname(token) for token in tokens):
        score += 1
    if any(_crm_is_patronymic(token) for token in tokens):
        score += 2
    if any(str(token or "").lower() in _CRM_NAME_STOPWORDS for token in tokens):
        score -= 3
    return score


def _crm_extract_name_from_sender(sender_name: Optional[str]) -> Optional[Dict[str, Any]]:
    raw = _crm_compact_text(sender_name)
    if not raw:
        return None

    raw = re.split(r"[,(/@|]+", raw, maxsplit=1)[0].strip()
    if not raw:
        return None

    best_tokens: Optional[List[str]] = None
    best_score = 0
    for match in _CRM_PERSON_SEQ_RE.finditer(raw):
        tokens = _CRM_NAME_TOKEN_RE.findall(match.group(1))[:3]
        score = _crm_score_name_tokens(tokens)
        if score > best_score:
            best_tokens = tokens
            best_score = score

    if not best_tokens or best_score < 2:
        return None
    parsed = _crm_parse_name_tokens(best_tokens)
    if not parsed:
        return None
    parsed["source"] = "sender_name"
    return parsed


def _crm_extract_name_from_text(text: Optional[str]) -> Optional[Dict[str, Any]]:
    raw = str(text or "")
    if not raw.strip():
        return None

    candidates: List[Dict[str, Any]] = []
    for pattern in _CRM_NAME_CONTEXT_PATTERNS:
        for match in pattern.finditer(raw):
            tokens = _CRM_NAME_TOKEN_RE.findall(match.group(1))[:3]
            score = _crm_score_name_tokens(tokens) + 2
            parsed = _crm_parse_name_tokens(tokens)
            if parsed and score >= 3:
                parsed["score"] = score
                parsed["source"] = "message_text"
                candidates.append(parsed)

    for match in _CRM_PERSON_SEQ_RE.finditer(raw):
        tokens = _CRM_NAME_TOKEN_RE.findall(match.group(1))[:3]
        score = _crm_score_name_tokens(tokens)
        parsed = _crm_parse_name_tokens(tokens)
        if parsed and score >= 3:
            parsed["score"] = score
            parsed["source"] = "message_text"
            candidates.append(parsed)

    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            int(item.get("name_components_count", 0)),
            int(item.get("score", 0)),
        ),
        reverse=True,
    )
    return candidates[0]


def _crm_normalize_phone(raw_phone: str) -> Optional[str]:
    raw = str(raw_phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if raw.startswith("+"):
        return f"+{digits}"
    if len(digits) in {10, 11, 12, 13, 14, 15}:
        if len(digits) == 10:
            return f"+7{digits}"
        return f"+{digits}"
    return None


def _crm_unique_list(values: List[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(str(value).strip())
    return result


def _crm_extract_emails(text: Optional[str]) -> List[str]:
    return _crm_unique_list(_CRM_EMAIL_RE.findall(str(text or "")))


def _crm_filter_phones_for_text(phones: List[str], text: Optional[str]) -> List[str]:
    raw_text = str(text or "")
    telemost_digits = [
        re.sub(r"\D", "", match)
        for match in _CRM_TELEMOST_URL_RE.findall(raw_text)
    ]
    telemost_digits = [value for value in telemost_digits if len(value) >= 8]
    if not telemost_digits:
        return _crm_unique_list(phones)

    clean: List[str] = []
    for phone in phones:
        phone_digits = re.sub(r"\D", "", str(phone or ""))
        if phone_digits and any(phone_digits == value or phone_digits in value for value in telemost_digits):
            continue
        clean.append(str(phone or ""))
    return _crm_unique_list(clean)


def _crm_sanitize_contact_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row or {})
    original_phones = list(item.get("phones") or [])
    clean_phones = _crm_filter_phones_for_text(original_phones, item.get("text"))
    if clean_phones != original_phones:
        item["phones"] = clean_phones
        if not clean_phones:
            item["match_sources"] = [
                source for source in list(item.get("match_sources") or []) if source != "phone"
            ]
            if isinstance(item.get("field_provenance"), dict):
                item["field_provenance"] = {
                    key: value for key, value in dict(item.get("field_provenance") or {}).items()
                    if key != "phone"
                }
    return item


def _crm_extract_phones(text: Optional[str]) -> List[str]:
    raw = _CRM_TELEMOST_URL_RE.sub(" ", str(text or ""))
    normalized: List[str] = []
    for match in _CRM_PHONE_RE.findall(raw):
        phone = _crm_normalize_phone(match)
        if phone:
            normalized.append(phone)
    return _crm_unique_list(normalized)


def _crm_extract_job_title(text: Optional[str]) -> Optional[str]:
    raw = _crm_compact_text(text)
    if not raw:
        return None
    match = _CRM_TITLE_RE.search(raw)
    if not match:
        return None
    title = _crm_compact_text(match.group(1))
    return title[:1].upper() + title[1:] if title else None


def _crm_extract_companies(text: Optional[str]) -> List[str]:
    raw = str(text or "")
    companies: List[str] = []
    for pattern in _CRM_COMPANY_PATTERNS:
        for match in pattern.finditer(raw):
            company = _crm_compact_text(match.group(1))
            if len(company) < 2:
                continue
            company = company.strip(".,;:!?)(")
            companies.append(company)
    return _crm_unique_list(companies)


def _crm_extract_city(text: Optional[str]) -> Optional[str]:
    raw = str(text or "")
    lowered = raw.lower()
    for alias, canonical in _CRM_CITY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return canonical

    for pattern in _CRM_CITY_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue
        candidate = _crm_compact_text(match.group(1))
        alias = candidate.lower()
        return _CRM_CITY_ALIASES.get(alias, _crm_title_case(candidate))
    return None


def _crm_pick_best_name(sender_candidate: Optional[Dict[str, Any]], text_candidate: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [item for item in [sender_candidate, text_candidate] if item]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            int(item.get("name_components_count", 0)),
            1 if item.get("source") == "message_text" else 0,
        ),
        reverse=True,
    )
    return candidates[0]


def _crm_extract_contact_from_record(
    lead_name: str,
    source_selector: Optional[str],
    rec: Dict[str, Any],
) -> Optional[CrmContactDTO]:
    msg = rec.get("message", {}) or {}
    sender = rec.get("sender", {}) or {}
    text = str(msg.get("text") or "").strip()
    sender_name = sender.get("name")
    sender_username = sender.get("username")

    sender_name_candidate = _crm_extract_name_from_sender(sender_name)
    text_name_candidate = _crm_extract_name_from_text(text)
    best_name = _crm_pick_best_name(sender_name_candidate, text_name_candidate)
    job_title = _crm_extract_job_title(text)
    companies = _crm_extract_companies(text)
    phones = _crm_extract_phones(text)
    emails = _crm_extract_emails(text)
    city = _crm_extract_city(text)

    if not any([best_name, job_title, companies, phones, emails, city]):
        return None

    match_sources: List[str] = []
    if sender_name_candidate:
        match_sources.append("sender_name")
    if text_name_candidate:
        match_sources.append("message_text")
    if job_title:
        match_sources.append("job_title")
    if companies:
        match_sources.append("company")
    if phones:
        match_sources.append("phone")
    if emails:
        match_sources.append("email")
    if city:
        match_sources.append("city")
    field_provenance = _crm_field_provenance_from_sources(
        sender_name_candidate=sender_name_candidate,
        text_name_candidate=text_name_candidate,
        job_title=job_title,
        companies=companies,
        phones=phones,
        emails=emails,
        city=city,
    )

    return CrmContactDTO(
        lead=lead_name,
        source_selector=source_selector,
        message_id=int(msg.get("id") or 0),
        date_utc=str(msg.get("date_utc") or ""),
        text=text,
        sender_username=sender_username,
        sender_name=sender_name,
        full_name=best_name.get("full_name") if best_name else None,
        first_name=best_name.get("first_name") if best_name else None,
        last_name=best_name.get("last_name") if best_name else None,
        patronymic=best_name.get("patronymic") if best_name else None,
        name_components_count=int(best_name.get("name_components_count", 0) if best_name else 0),
        job_title=job_title,
        companies=companies,
        phones=phones,
        emails=emails,
        city=city,
        match_sources=_crm_unique_list(match_sources),
        field_provenance=field_provenance,
    )


def _collect_crm_contacts(
    limit: int = 1000,
    lead_filter: Optional[str] = None,
    query: Optional[str] = None,
) -> List[CrmContactDTO]:
    _ensure_dir_exists()
    selector_map = _managed_selector_map()
    rows: List[CrmContactDTO] = []
    lead_filter_value = str(lead_filter or "").strip().lower()
    query_value = str(query or "").strip().lower()

    for jf in PAYME_OUT_DIR.glob("*.jsonl"):
        lead_name = jf.stem
        source_selector = selector_map.get(lead_name.lower())

        if lead_filter_value:
            lead_hay = f"{lead_name} {source_selector or ''}".lower()
            if lead_filter_value not in lead_hay:
                continue

        for rec in _iter_jsonl(jf):
            row = _crm_extract_contact_from_record(lead_name, source_selector, rec)
            if not row:
                continue
            if query_value:
                row_hay = " ".join(
                    [
                        row.lead,
                        row.source_selector or "",
                        row.sender_username or "",
                        row.sender_name or "",
                        row.full_name or "",
                        row.job_title or "",
                        " ".join(row.companies),
                        " ".join(row.phones),
                        " ".join(row.emails),
                        row.city or "",
                        row.text or "",
                    ]
                ).lower()
                if query_value not in row_hay:
                    continue
            rows.append(row)

    rows.sort(
        key=lambda item: (
            item.date_utc or "",
            item.message_id,
        ),
        reverse=True,
    )
    return rows[: max(limit, 1)]


def _telegram_session_file_path() -> Path:
    session_path = Path(SESSION)
    if session_path.suffix == ".session":
        return session_path
    return session_path.with_suffix(".session")




def _openrouter_model_from_raw(item: Dict[str, Any]) -> OpenRouterModelDTO:
    model_id = str(item.get("id") or item.get("slug") or "").strip()
    name = str(item.get("name") or model_id or "").strip()
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    prompt_price = str(pricing.get("prompt") if pricing.get("prompt") is not None else "").strip()
    completion_price = str(pricing.get("completion") if pricing.get("completion") is not None else "").strip()

    def _is_zero_price(value: str) -> bool:
        if value in {"", "0", "0.0", "0.00", "0.000000"}:
            return True
        try:
            return float(value) == 0.0
        except ValueError:
            return False

    is_free = model_id.endswith(":free") or (_is_zero_price(prompt_price) and _is_zero_price(completion_price))
    context_length = item.get("context_length")
    try:
        context_length_value = int(context_length) if context_length is not None else None
    except (TypeError, ValueError):
        context_length_value = None
    return OpenRouterModelDTO(
        id=model_id or DEFAULT_OPENROUTER_MODEL_ID,
        name=name or model_id or DEFAULT_OPENROUTER_MODEL_ID,
        context_length=context_length_value,
        free=is_free,
        pricing_prompt=prompt_price or None,
        pricing_completion=completion_price or None,
    )


def _fallback_openrouter_models() -> List[OpenRouterModelDTO]:
    return [OpenRouterModelDTO(**item) for item in _OPENROUTER_FALLBACK_MODELS]


def _list_openrouter_models_sync(query: str = "", include_paid: bool = False) -> OpenRouterModelsDTO:
    normalized_query = str(query or "").strip().lower()
    settings = _get_app_settings()
    api_key = str(settings.get("openrouter_api_key") or "").strip()
    source = "fallback"
    message = "Показан локальный fallback-список моделей."
    models: List[OpenRouterModelDTO] = []

    try:
        headers = {
            "Accept": "application/json",
            "HTTP-Referer": "http://localhost:8001",
            "X-Title": PROJECT_NAME,
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=_openrouter_timeout_sec())
        response.raise_for_status()
        payload = response.json()
        raw_items = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(raw_items, list):
            models = [_openrouter_model_from_raw(item) for item in raw_items if isinstance(item, dict)]
            source = "openrouter"
            message = "Модели загружены из OpenRouter."
    except Exception as exc:
        models = _fallback_openrouter_models()
        message = f"OpenRouter сейчас недоступен, показан fallback: {exc}"

    if not models:
        models = _fallback_openrouter_models()

    filtered: List[OpenRouterModelDTO] = []
    for model in models:
        if not include_paid and not model.free:
            continue
        haystack = f"{model.id} {model.name}".lower()
        if normalized_query and normalized_query not in haystack:
            continue
        filtered.append(model)

    filtered.sort(key=lambda model: (not model.free, model.name.lower(), model.id.lower()))
    return OpenRouterModelsDTO(items=filtered[:500], total=len(filtered), source=source, message=message)


# --------- РОУТЫ -----------




















@app.post("/api/payme/license/update", response_model=XFilesLicenseActionDTO, tags=["payme"])
def api_payme_license_update(payload: XFilesLicenseActivatePayload):
    return _xfiles_apply_invite_license(
        payload,
        action="update",
        allowed_kinds={"activation", "renewal", "trial-extension", "upgrade", "addon", "update", "support"},
        success_message="Лицензия обновлена",
    )






















































































def _require_confirmed_full_refresh(force_full: bool, confirm_full_refresh: bool, label: str) -> None:
    if force_full and not confirm_full_refresh:
        raise HTTPException(
            status_code=409,
            detail=f"{label}: полный пересчёт требует явного подтверждения confirm_full_refresh=true",
        )
















































def _xfiles_deal_cache_status_log(message: str) -> None:
    now = _utc_now().isoformat()
    line = f"{now} {str(message or '').strip()}"
    with _xfiles_deal_cache_warm_status_lock:
        log_rows = list(_xfiles_deal_cache_warm_status.get("progress_log") or [])
        log_rows.append(line)
        _xfiles_deal_cache_warm_status["progress_log"] = log_rows[-max(1, _XFILES_DEAL_CACHE_PROGRESS_LOG_LIMIT):]
        _xfiles_deal_cache_warm_status["updated_at"] = now


def _xfiles_deal_cache_status_snapshot() -> Dict[str, Any]:
    with _xfiles_deal_cache_warm_status_lock:
        return dict(_xfiles_deal_cache_warm_status)


def _xfiles_deal_cache_warm_steps() -> List[Dict[str, Any]]:
    return [
        {
            "label": "Статус сделок",
            "cache_key": "xfiles_deals_status",
            "factory": _xfiles_deals_status_sync,
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Список сделок",
            "cache_key": "xfiles_deals:1:10:5000::",
            "factory": lambda: XFilesDealsPageDTO(**_paginate_items(_xfiles_load_deals(limit=5000), page=1, page_size=10)),
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Kanban сделок",
            "cache_key": "xfiles_deals_kanban:::20",
            "factory": lambda: _xfiles_deals_kanban_sync(limit_per_stage=20),
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Аудит сделок",
            "cache_key": "xfiles_deals_audit:1:10:200",
            "factory": lambda: XFilesDealAuditPageDTO(**_paginate_items(_xfiles_load_deal_audit(limit=200), page=1, page_size=10)),
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Напоминания",
            "cache_key": "xfiles_deal_reminders:50:False",
            "factory": lambda: _xfiles_deal_reminders_sync(limit=50, include_done=False),
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Конверсия",
            "cache_key": "xfiles_deal_conversion",
            "factory": _xfiles_deal_conversion_sync,
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Оптимизация прибыли",
            "cache_key": "xfiles_profit_optimization",
            "factory": _xfiles_profit_optimization_sync,
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Возможности сделок",
            "cache_key": "xfiles_deal_opportunities:20",
            "factory": lambda: _xfiles_deal_opportunities_sync(limit=20),
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "North Star",
            "cache_key": "xfiles_north_star",
            "factory": _xfiles_north_star_sync,
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Шаблоны договоров",
            "cache_key": "xfiles_contract_templates",
            "factory": _xfiles_contract_templates_page_sync,
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "Метрики договоров",
            "cache_key": "xfiles_contract_metrics",
            "factory": _xfiles_contract_metrics_sync,
            "ttl": _XFILES_DEAL_API_CACHE_TTL_SEC,
        },
        {
            "label": "План продаж по событиям",
            "cache_key": "xfiles_event_sales_plan:10",
            "factory": lambda: _xfiles_event_sales_plan_sync(limit=10),
            "ttl": 20,
        },
        {
            "label": "Контакты дня",
            "cache_key": "xfiles_daily_contacts:10:all",
            "factory": lambda: _xfiles_daily_contacts_sync(limit=10, lead_temperature="all"),
            "ttl": 20,
        },
    ]


def _xfiles_deal_cache_warm_sync(reason: str = "background") -> None:
    steps = _xfiles_deal_cache_warm_steps()
    now = _utc_now().isoformat()
    with _xfiles_deal_cache_warm_status_lock:
        if not _xfiles_deal_cache_warm_status.get("running"):
            _xfiles_deal_cache_warm_status["started_at"] = now
            _xfiles_deal_cache_warm_status["progress_log"] = []
        _xfiles_deal_cache_warm_status.update(
            {
                "running": True,
                "finished_at": None,
                "updated_at": now,
                "progress_current": 0,
                "progress_total": len(steps),
                "progress_percent": 0.0,
                "current_item": None,
                "last_error": None,
                "last_reason": str(reason or "background"),
            }
        )
    _xfiles_deal_cache_status_log(f"Прогрев кеша сделок запущен: {reason}")
    for index, step in enumerate(steps, start=1):
        label = str(step.get("label") or step.get("cache_key") or "")
        cache_key = str(step.get("cache_key") or "")
        with _xfiles_deal_cache_warm_status_lock:
            _xfiles_deal_cache_warm_status["current_item"] = label
            _xfiles_deal_cache_warm_status["updated_at"] = _utc_now().isoformat()
        try:
            value = step["factory"]()
            _api_snapshot_cache_set(cache_key, value, ttl_sec=float(step.get("ttl") or _XFILES_DEAL_API_CACHE_TTL_SEC))
            _xfiles_deal_cache_status_log(f"{label}: кеш обновлён")
        except Exception as exc:
            message = f"{label}: ошибка прогрева кеша: {exc}"
            with _xfiles_deal_cache_warm_status_lock:
                _xfiles_deal_cache_warm_status["last_error"] = str(exc)
            _xfiles_deal_cache_status_log(message)
        finally:
            with _xfiles_deal_cache_warm_status_lock:
                _xfiles_deal_cache_warm_status["progress_current"] = index
                _xfiles_deal_cache_warm_status["progress_percent"] = round(index / max(1, len(steps)) * 100.0, 1)
                _xfiles_deal_cache_warm_status["updated_at"] = _utc_now().isoformat()
    finished_at = _utc_now().isoformat()
    with _xfiles_deal_cache_warm_status_lock:
        _xfiles_deal_cache_warm_status.update(
            {
                "running": False,
                "finished_at": finished_at,
                "updated_at": finished_at,
                "current_item": None,
                "progress_current": len(steps),
                "progress_total": len(steps),
                "progress_percent": 100.0,
            }
        )
    _xfiles_deal_cache_status_log("Прогрев кеша сделок завершён")


def _xfiles_schedule_deal_cache_warmup(reason: str = "background") -> bool:
    if not _XFILES_DEAL_CACHE_WARMUP_ENABLED:
        return False
    now = _utc_now().isoformat()
    with _xfiles_deal_cache_warm_status_lock:
        if _xfiles_deal_cache_warm_status.get("running"):
            return False
        _xfiles_deal_cache_warm_status.update(
            {
                "running": True,
                "started_at": now,
                "finished_at": None,
                "updated_at": now,
                "progress_current": 0,
                "progress_total": 0,
                "progress_percent": 0.0,
                "current_item": None,
                "last_error": None,
                "last_reason": str(reason or "background"),
                "progress_log": [],
            }
        )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        thread = threading.Thread(
            target=_xfiles_deal_cache_warm_sync,
            args=(reason,),
            name="xfiles-deal-cache-warmup",
            daemon=True,
        )
        thread.start()
        return True
    loop.create_task(asyncio.to_thread(_xfiles_deal_cache_warm_sync, reason))
    return True






















































async def _sse_lead_events(lead_filter: Optional[str] = None, heartbeat_sec: int = 15):
    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        _lead_event_subscribers.add(queue)
        last_ping = asyncio.get_event_loop().time()
        target = str(lead_filter or "").strip().lower()

        try:
            while True:
                timeout = max(0.1, heartbeat_sec - (asyncio.get_event_loop().time() - last_ping))
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=timeout)
                    if target:
                        event_lead = str(event.get("lead") or "").strip().lower()
                        if event_lead != target:
                            continue
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
                    last_ping = asyncio.get_event_loop().time()
        finally:
            _lead_event_subscribers.discard(queue)

    return event_stream


def _typed_stream_packet(event_type: str, payload: Any) -> bytes:
    body = {
        "type": str(event_type or "").strip(),
        "ts": _utc_now().isoformat(),
        "payload": payload,
    }
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n".encode("utf-8")






def _resolve_lead_basename(lead: str) -> Optional[str]:
    """
    Возвращает фактическое имя файла без расширения для лида (с учётом регистра),
    или None если не найден *.jsonl.
    """
    jf = PAYME_OUT_DIR / f"{lead}.jsonl"
    if jf.exists():
        return jf.stem
    # нечувствительно к регистру
    for p in PAYME_OUT_DIR.glob("*.jsonl"):
        if p.stem.lower() == lead.lower():
            return p.stem
    return None


def _read_tokens_value(stem: str) -> str:
    calc_path = PAYME_OUT_DIR / f"{stem}-tokens-calculated.txt"
    if calc_path.exists():
        try:
            raw = calc_path.read_text(encoding="utf-8", errors="replace").strip()
            if raw:
                return raw
        except Exception:
            pass

    jsonl_path = PAYME_OUT_DIR / f"{stem}.jsonl"
    if not jsonl_path.exists():
        return "0"

    total = 0
    for rec in _iter_jsonl(jsonl_path):
        msg = rec.get("message", {})
        sender = rec.get("sender", {})
        combined = " | ".join(
            [
                str(msg.get("date_utc") or ""),
                str(sender.get("name") or sender.get("username") or ""),
                str(msg.get("text") or ""),
            ]
        )
        total += max(1, len(combined.encode("utf-8")) // 4)
    return str(total)


def _build_tokens_payload(stem: str) -> Dict[str, Any]:
    jsonl_path = PAYME_OUT_DIR / f"{stem}.jsonl"
    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")

    messages: List[Dict[str, Any]] = []
    total_tokens = 0

    for rec in _iter_jsonl(jsonl_path):
        msg = rec.get("message", {})
        sender = rec.get("sender", {})
        chat = rec.get("chat", {})

        name = sender.get("name") or sender.get("username") or chat.get("title")
        text = msg.get("text") or rec.get("text")
        date_utc = msg.get("date_utc") or rec.get("date_utc") or msg.get("date")

        combined = " | ".join(
            [
                str(date_utc or "null"),
                str(name or "null"),
                str(text or "null"),
            ]
        )

        messages.append(
            {
                "date_utc": date_utc,
                "name": name,
                "text": text,
                "combined": combined,
            }
        )
        total_tokens += max(1, len(combined.encode("utf-8")) // 4)

    return {
        "source": str(jsonl_path),
        "total_messages": len(messages),
        "messages": messages,
        "total_tokens": total_tokens,
    }


def _estimate_chat_tokens(text: Any) -> int:
    value = str(text or "").strip()
    if not value:
        return 0
    # Fast deterministic estimate: close enough for planning context windows, no LLM call needed.
    return max(1, len(value.encode("utf-8")) // 4)


def _iter_lead_analysis_messages(lead: str) -> List[Dict[str, Any]]:
    stem = _resolve_lead_basename(lead) or str(lead or "").strip()
    jsonl_path = PAYME_OUT_DIR / f"{stem}.jsonl"
    if not stem or not jsonl_path.exists():
        return []

    items: List[Dict[str, Any]] = []
    for index, rec in enumerate(_iter_jsonl(jsonl_path), start=1):
        if not isinstance(rec, dict):
            continue
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        sender = rec.get("sender") if isinstance(rec.get("sender"), dict) else {}
        chat = rec.get("chat") if isinstance(rec.get("chat"), dict) else {}
        raw_id = msg.get("id") or rec.get("id") or rec.get("message_id") or index
        try:
            message_id = int(raw_id)
        except Exception:
            message_id = index
        text = str(msg.get("text") or rec.get("text") or "").strip()
        date_utc = str(msg.get("date_utc") or rec.get("date_utc") or msg.get("date") or "").strip()
        sender_id = str(sender.get("id") or "").strip()
        sender_username = str(sender.get("username") or "").strip()
        sender_name = str(sender.get("name") or sender_username or chat.get("title") or "unknown").strip()
        sender_key = sender_id or sender_username or sender_name or "unknown"
        combined = " | ".join([date_utc, sender_name, sender_username, text])
        items.append(
            {
                "id": message_id,
                "message_id": message_id,
                "date_utc": date_utc,
                "text": text,
                "sender_id": sender_id,
                "sender_username": sender_username,
                "sender_name": sender_name,
                "sender_key": sender_key,
                "tokens": _estimate_chat_tokens(combined),
            }
        )

    items.sort(key=lambda item: (str(item.get("date_utc") or ""), int(item.get("message_id") or 0)))
    return items


from app.services.chat_analysis import (
    _chat_analysis_history_for_lead,
    _chat_analysis_history_state,
    _chat_analysis_stats_payload,
    _run_chat_analysis_sync,
    send_to_llm_and_store_response,
)







def _save_chat_analysis_item(lead: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = _chat_analysis_history_state()
    by_lead = state.setdefault("items_by_lead", {})
    items = [old for old in by_lead.get(str(lead), []) if old.get("analysis_id") != item.get("analysis_id")]
    items.insert(0, item)
    by_lead[str(lead)] = items[:CHAT_ANALYSIS_HISTORY_MAX_ITEMS]
    state["updated_at"] = _utc_now().isoformat()
    telegram_sync.save_state()
    return by_lead[str(lead)]


def _select_chat_analysis_messages(lead: str, payload: ChatAnalysisPayload) -> List[Dict[str, Any]]:
    messages = [item for item in _iter_lead_analysis_messages(lead) if str(item.get("text") or "").strip()]
    sender_key = str(getattr(payload, "sender_key", "") or "").strip()
    if sender_key:
        messages = [item for item in messages if str(item.get("sender_key") or "unknown") == sender_key]
    if payload.mode == "all":
        return messages
    if payload.mode == "selected":
        selected = {int(value) for value in payload.selected_message_ids if str(value).strip().lstrip("-").isdigit()}
        return [item for item in messages if int(item.get("message_id") or 0) in selected]
    newest = list(reversed(messages))
    if payload.mode == "token_budget":
        chosen: List[Dict[str, Any]] = []
        tokens = 0
        for item in newest:
            next_tokens = int(item.get("tokens") or 0)
            if chosen and tokens + next_tokens > payload.token_budget:
                break
            chosen.append(item)
            tokens += next_tokens
        return list(reversed(chosen))
    limit = max(1, int(payload.message_limit or 10))
    return messages[-limit:]


def _chat_analysis_context(messages: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for item in messages:
        date_utc = str(item.get("date_utc") or "—")
        sender = str(item.get("sender_name") or item.get("sender_username") or item.get("sender_key") or "unknown")
        text = str(item.get("text") or "").strip()
        lines.append(f"[{date_utc}] {sender}: {text}")
    return "\n".join(lines)


def _call_lmstudio_chat_completion_sync(
    *,
    kind: str,
    base_url: str,
    payload: Dict[str, Any],
    input_ids: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    base = str(base_url or DEFAULT_LMSTUDIO_BASE_URL).strip().rstrip("/") or DEFAULT_LMSTUDIO_BASE_URL
    started_at = _utc_now()
    started_monotonic = time.monotonic()
    model = str(payload.get("model") or "")
    response_payload: Optional[Dict[str, Any]] = None
    result_text = ""
    try:
        response = requests.post(
            f"{base}/chat/completions",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=payload,
            timeout=_openrouter_timeout_sec(),
        )
        response.raise_for_status()
        raw_payload = response.json()
        response_payload = raw_payload if isinstance(raw_payload, dict) else {}
        try:
            result_text = str(response_payload["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            result_text = ""
        _record_llm_audit(
            kind=kind,
            provider="lmstudio",
            model=model,
            request_payload=payload,
            input_ids=input_ids,
            started_at=started_at,
            duration_sec=time.monotonic() - started_monotonic,
            status="ready",
            result_text=result_text,
            response_payload=response_payload,
        )
        return response_payload, result_text
    except Exception as exc:
        _record_llm_audit(
            kind=kind,
            provider="lmstudio",
            model=model,
            request_payload=payload,
            input_ids=input_ids,
            started_at=started_at,
            duration_sec=time.monotonic() - started_monotonic,
            status="error",
            result_text=result_text,
            response_payload=response_payload,
            error=str(exc),
        )
        raise




def _ensure_tokens_artifacts(stem: str) -> Dict[str, Path]:
    payload = _build_tokens_payload(stem)

    tokens_txt_path = PAYME_OUT_DIR / f"{stem}-tokens.txt"
    tokens_json_path = PAYME_OUT_DIR / f"{stem}-tokens.json"
    tokens_calc_path = PAYME_OUT_DIR / f"{stem}-tokens-calculated.txt"

    with tokens_txt_path.open("w", encoding="utf-8") as file:
        for item in payload["messages"]:
            file.write(f"{item['combined']}\n")

    tokens_json_path.write_text(
        json.dumps(
            {
                "source": payload["source"],
                "total_messages": payload["total_messages"],
                "messages": payload["messages"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tokens_calc_path.write_text(f"{payload['total_tokens']}\n", encoding="utf-8")

    return {
        "tokens_txt": tokens_txt_path,
        "tokens_json": tokens_json_path,
        "tokens_calc": tokens_calc_path,
    }


def _normalize_llm_response_items(raw_text: str) -> List[str]:
    text = raw_text.strip()
    if not text:
        return []

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text, count=1)
        text = text.strip()

    items: List[str] = []

    button_matches = re.findall(r"<button\b[^>]*>(.*?)</button>", text, flags=re.IGNORECASE | re.DOTALL)
    if button_matches:
        for candidate in button_matches:
            cleaned = re.sub(r"<[^>]+>", " ", candidate)
            cleaned = html.unescape(" ".join(cleaned.split()))
            if cleaned:
                items.append(cleaned)
        return items

    text = re.sub(r"<\s*hr\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)

    for line in text.splitlines():
        cleaned = " ".join(line.split())
        cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", cleaned)
        if cleaned:
            items.append(cleaned)

    if items:
        return items

    fallback = " ".join(text.split())
    return [fallback] if fallback else []


def _collect_llm_responses(stem: str) -> List[str]:
    lead_dir = PAYME_OUT_DIR / stem
    if not lead_dir.exists():
        return []

    responses: List[str] = []
    seen: set[str] = set()
    for path in sorted(lead_dir.glob("*/response.txt"), reverse=True):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        for item in _normalize_llm_response_items(text):
            if item in seen:
                continue
            seen.add(item)
            responses.append(item)
            if len(responses) >= 3:
                return responses
    return responses[:3]


def _build_llm_buttons_html(stem: str) -> str:
    responses = _collect_llm_responses(stem)
    if not responses:
        responses = ["... ответ1 ...", "... ответ2 ...", "... ответ3 ..."]

    parts: List[str] = []
    for idx, text in enumerate(responses, start=1):
        compact = " ".join(text.split())
        label = compact[:220] + ("..." if len(compact) > 220 else "")
        safe_label = html.escape(label or f"... ответ{idx} ...")
        safe_text = html.escape(text, quote=True)
        parts.append(
            f'<button type="button" class="llm-btn" data-text="{safe_text}">{safe_label}</button>'
        )
    return "\n".join(parts)


def _render_llm_html(stem: str) -> str:
    if not LLM_TEMPLATE_PATH.exists():
        return ""

    template = LLM_TEMPLATE_PATH.read_text(encoding="utf-8", errors="replace")
    return (
        template
        .replace("{tokens}", _read_tokens_value(stem))
        .replace("{button}", _build_llm_buttons_html(stem))
    )


def _ensure_llm_html(stem: str) -> Optional[Path]:
    content = _render_llm_html(stem)
    if not content:
        return None

    html_path = PAYME_OUT_DIR / f"{stem}-llm.html"
    html_path.write_text(content, encoding="utf-8")
    return html_path













from app.core.lifespan import register_runtime_lifespan

register_runtime_lifespan(app, globals())
















# Compatibility: extracted route handlers now live in app.services.*.
_EXTRACTED_SERVICE_BY_HANDLER = {
    "list_leads": "app.services.legacy_api",
    "get_lead": "app.services.legacy_api",
    "create_lead": "app.services.legacy_api",
    "update_lead": "app.services.legacy_api",
    "delete_lead": "app.services.legacy_api",
    "create_message": "app.services.legacy_api",
    "api_payme_jur_entities": "app.services.jur_entities",
    "api_payme_jur_entities_sync": "app.services.jur_entities",
    "api_payme_jur_entities_parser_add": "app.services.jur_entities",
    "api_payme_jur_entities_parser_remove": "app.services.jur_entities",
    "api_payme_images": "app.services.media",
    "api_payme_image_text": "app.services.media",
    "api_payme_media_config": "app.services.media",
    "api_payme_media_status": "app.services.media",
    "api_payme_media_add": "app.services.media",
    "api_payme_media_add_many": "app.services.media",
    "api_payme_media_remove": "app.services.media",
    "api_payme_media_clear": "app.services.media",
    "api_payme_media_clear_all": "app.services.media",
    "api_payme_images_ocr_pending": "app.services.media",
    "api_payme_search_messages": "app.services.search",
    "api_payme_search_context": "app.services.search",
    "api_payme_deals_status": "app.services.deals",
    "api_payme_deals_reminders": "app.services.deals",
    "api_payme_deals_conversion": "app.services.deals",
    "api_payme_deals_profit_optimization": "app.services.deals",
    "api_payme_deals_opportunities": "app.services.deals",
    "api_payme_deals_north_star": "app.services.deals",
    "api_payme_deals": "app.services.deals",
    "api_payme_deals_kanban": "app.services.deals",
    "api_payme_deals_audit": "app.services.deals",
    "api_payme_deals_contract_templates": "app.services.deals",
    "api_payme_deals_contract_metrics": "app.services.deals",
    "api_payme_deals_product_margins": "app.services.deals",
    "api_payme_deals_product_margin_upsert": "app.services.deals",
    "api_payme_deals_product_margin_delete": "app.services.deals",
    "api_payme_deals_create": "app.services.deals",
    "api_payme_deals_event_sales_plan": "app.services.deals",
    "api_payme_deal_assistant": "app.services.deals",
    "api_payme_deal_negotiation_brief": "app.services.deals",
    "api_payme_deal_contract_kit": "app.services.deals",
    "api_payme_deal_contract_status": "app.services.deals",
    "api_payme_deals_update": "app.services.deals",
    "api_payme_deals_delete": "app.services.deals",
    "api_payme_deals_from_outreach": "app.services.deals",
    "api_payme_deal_follow_up_sequence": "app.services.deals",
    "api_payme_deals_daily_contacts": "app.services.deals",
    "api_payme_needs_signals": "app.services.deals",
    "api_payme_license_activate": "app.services.license",
    "api_payme_license_audit": "app.services.license",
    "api_payme_license_email_import": "app.services.license",
    "api_payme_license_menus": "app.services.license",
    "api_payme_license_menus_check": "app.services.license",
    "api_payme_license_renew": "app.services.license",
    "api_payme_license_status": "app.services.license",
    "api_payme_license_upgrade": "app.services.license",
    "api_payme_tariffs": "app.services.license",
    "api_payme_update_status": "app.services.license",
    "api_payme_all_leads_stream": "app.services.leads",
    "api_payme_lead_analysis_history": "app.services.leads",
    "api_payme_lead_analysis_run": "app.services.leads",
    "api_payme_lead_analysis_stats": "app.services.leads",
    "api_payme_lead_llm": "app.services.leads",
    "api_payme_lead_messages": "app.services.leads",
    "api_payme_leads_activate": "app.services.leads",
    "api_payme_leads_deactivate": "app.services.leads",
    "api_payme_leads_delete": "app.services.leads",
    "api_payme_leads_group": "app.services.leads",
    "api_payme_list_leads": "app.services.leads",
    "api_payme_llm_run": "app.services.leads",
    "api_payme_send": "app.services.leads",
    "api_payme_stream": "app.services.leads",
    "api_payme_import_sync_disable": "app.services.channels",
    "api_payme_import_sync_enable": "app.services.channels",
    "api_payme_import_sync_status": "app.services.channels",
    "api_payme_source_add": "app.services.channels",
    "api_payme_source_policies": "app.services.channels",
    "api_payme_source_policy": "app.services.channels",
    "api_payme_source_reload": "app.services.channels",
    "api_payme_source_remove": "app.services.channels",
    "api_payme_telegram_dialogs": "app.services.channels",
    "api_payme_telegram_dialogs_import": "app.services.channels",
    "api_payme_telegram_dialogs_remove_added": "app.services.channels",
    "api_payme_telegram_dialogs_settings": "app.services.channels",
    "api_payme_telegram_sync_control": "app.services.channels",
    "api_payme_telegram_sync_pause": "app.services.channels",
    "api_payme_telegram_sync_resume": "app.services.channels",
    "api_payme_routes_addresses": "app.services.routes",
    "api_payme_routes_geocode": "app.services.routes",
    "api_payme_routes_map_points": "app.services.routes",
    "api_payme_routes_messages": "app.services.routes",
    "api_payme_routes_refresh": "app.services.routes",
    "api_payme_routes_status": "app.services.routes",
    "api_payme_auth_api_credentials": "app.services.config",
    "api_payme_auth_code": "app.services.config",
    "api_payme_auth_logout": "app.services.config",
    "api_payme_auth_password": "app.services.config",
    "api_payme_auth_phone": "app.services.config",
    "api_payme_auth_reauthorize": "app.services.config",
    "api_payme_openrouter_models": "app.services.config",
    "api_payme_settings": "app.services.config",
    "api_payme_settings_save": "app.services.config",
    "api_payme_system_reset_data": "app.services.config",
    "api_payme_system_reset_data_status": "app.services.config",
    "api_payme_dashboard_summary": "app.services.monitoring",
    "api_payme_duckdb_archive_legacy_cache": "app.services.monitoring",
    "api_payme_duckdb_export_parquet": "app.services.monitoring",
    "api_payme_duckdb_materialize_parquet_sidecars": "app.services.monitoring",
    "api_payme_duckdb_refresh": "app.services.monitoring",
    "api_payme_duckdb_status": "app.services.monitoring",
    "api_payme_monitor_stream": "app.services.monitoring",
    "api_payme_realtime_stream": "app.services.monitoring",
    "api_payme_runtime_logs": "app.services.monitoring",
    "api_payme_runtime_logs_stream": "app.services.monitoring",
    "api_payme_runtime_status": "app.services.monitoring",
    "api_payme_server_status": "app.services.monitoring",
    "api_payme_system_metrics": "app.services.monitoring",
    "api_payme_lead_analysis_history": "app.services.analysis",
    "api_payme_lead_analysis_run": "app.services.analysis",
    "api_payme_lead_analysis_stats": "app.services.analysis",
    "api_payme_llm_run": "app.services.analysis",
    "api_payme_calendar_events": "app.services.events",
    "api_payme_event_keywords": "app.services.events",
    "api_payme_event_keywords_update": "app.services.events",
    "api_payme_event_message_delete": "app.services.events",
    "api_payme_event_messages": "app.services.events",
    "api_payme_events_config": "app.services.events",
    "api_payme_events_refresh": "app.services.events",
    "api_payme_events_status": "app.services.events",
    "api_payme_crm_cleanup_telemost_phones": "app.services.crm",
    "api_payme_crm_config": "app.services.crm",
    "api_payme_crm_contacts": "app.services.crm",
    "api_payme_crm_refresh": "app.services.crm",
    "api_payme_crm_status": "app.services.crm",
    "api_payme_outreach_add_item": "app.services.outreach",
    "api_payme_outreach_delete_item": "app.services.outreach",
    "api_payme_outreach_expand_values": "app.services.outreach",
    "api_payme_outreach_items": "app.services.outreach",
    "api_payme_outreach_sequence_create": "app.services.outreach",
    "api_payme_outreach_sequence_from_enreach": "app.services.outreach",
    "api_payme_outreach_sequence_update": "app.services.outreach",
    "api_payme_outreach_sequences": "app.services.outreach",
    "api_payme_outreach_stats": "app.services.outreach",
    "api_payme_outreach_touch_status": "app.services.outreach",
    "api_payme_contact_do_not_contact": "app.services.contacts",
    "api_payme_contact_messages": "app.services.contacts",
    "api_payme_contact_qualification_prompts": "app.services.contacts",
    "api_payme_contact_qualifications": "app.services.contacts",
    "api_payme_contact_qualify": "app.services.contacts",
    "api_payme_contacts": "app.services.contacts",
    "api_payme_contacts_chats": "app.services.contacts",
    "api_payme_contacts_config": "app.services.contacts",
    "api_payme_contacts_refresh": "app.services.contacts",
    "api_payme_contacts_status": "app.services.contacts",
}

refresh_legacy_globals()
from app.storage.duckdb_store import refresh_legacy_globals as refresh_duckdb_legacy_globals
from app.core.app_settings import refresh_legacy_globals as refresh_app_settings_legacy_globals
from app.services.runtime_status import refresh_legacy_globals as refresh_runtime_status_legacy_globals
from app.workers.analysis_cache import refresh_legacy_globals as refresh_analysis_cache_legacy_globals
from app.services.llm_client import refresh_legacy_globals as refresh_llm_client_legacy_globals
from app.services.chat_analysis import refresh_legacy_globals as refresh_chat_analysis_legacy_globals
from app.services.media_assets import refresh_legacy_globals as refresh_media_assets_legacy_globals
from app.services.contact_llm_runtime import refresh_legacy_globals as refresh_contact_llm_legacy_globals
from app.services.xfiles_deals_engine import refresh_legacy_globals as refresh_xfiles_deals_engine_legacy_globals
from app.services.xfiles_contracts import refresh_legacy_globals as refresh_xfiles_contracts_legacy_globals
refresh_duckdb_legacy_globals()
refresh_app_settings_legacy_globals()
refresh_runtime_status_legacy_globals()
refresh_analysis_cache_legacy_globals()
refresh_llm_client_legacy_globals()
refresh_chat_analysis_legacy_globals()
refresh_media_assets_legacy_globals()
refresh_contact_llm_legacy_globals()
refresh_xfiles_deals_engine_legacy_globals()
refresh_xfiles_contracts_legacy_globals()

def __getattr__(name: str):
    module_name = _EXTRACTED_SERVICE_BY_HANDLER.get(name)
    if module_name:
        from importlib import import_module

        return getattr(import_module(module_name), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
