"""Runtime status helpers extracted from the legacy backend."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, Optional

from app.core.error_taxonomy import classify_error_text, recovery_hint
from app.services.dashboard_source_stats import build_dashboard_scanned_sources_payload

_RUNTIME_STATUS_TELEGRAM_AUTH_TIMEOUT_SEC = max(
    0.1,
    float(os.environ.get("XFILES_RUNTIME_STATUS_AUTH_TIMEOUT_SEC", "0.6") or "0.6"),
)
_RUNTIME_STATUS_TELEGRAM_AUTOSTART_ENABLED = (
    os.environ.get("XFILES_RUNTIME_STATUS_TELEGRAM_AUTOSTART", "0") == "1"
)


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime")
    legacy_back = sys.modules.get("back")
    for source in (runtime, legacy_back):
        if source is None:
            continue
        for name, value in vars(source).items():
            if not name.startswith("__") and name != "refresh_legacy_globals":
                globals()[name] = value


refresh_legacy_globals()


def _telegram_job_runtime_state() -> Dict[str, Any]:
    """Best-effort non-blocking view of the durable Telegram worker state."""
    state: Dict[str, Any] = {
        "worker_connected": False,
        "sync_reading": False,
        "sync_reading_stage": None,
        "status_detail": "",
    }
    try:
        from app.services import jobs as jobs_service

        job = jobs_service.latest_active_job_by_type("telegram_sync") or jobs_service.latest_job_by_type("telegram_sync")
        if job is None:
            state["status_detail"] = "Telegram worker job отсутствует"
            return state
        job_status = str(getattr(job, "status", "") or "").lower()
        result = getattr(job, "result", None)
        if not isinstance(result, dict):
            result = {}
        active_sources = result.get("active_sources") if isinstance(result, dict) else []
        if not isinstance(active_sources, list):
            active_sources = []
        state["worker_connected"] = job_status in {"running", "queued", "pending"} and not jobs_service.is_stale_telegram_sync_job(job)
        state["sync_reading"] = bool(active_sources) or int(getattr(job, "chunks_done", 0) or 0) < int(
            getattr(job, "chunks_total", 0) or 0
        ) and job_status in {"running", "queued", "pending"}
        first_active = next((item for item in active_sources if isinstance(item, dict)), None)
        if first_active:
            state["sync_reading_stage"] = str(
                first_active.get("stage") or first_active.get("read_stage") or first_active.get("status") or ""
            ).strip() or None
        state["status_detail"] = str(
            getattr(job, "progress_label", "")
            or result.get("message")
            or result.get("reason")
            or f"Telegram worker: {job_status or 'unknown'}"
        )
    except Exception as exc:
        state["status_detail"] = f"Telegram worker status недоступен: {exc}"
    return state


def _runtime_status_telegram_flags(
    *,
    connected: bool,
    authorized: Optional[bool],
) -> Dict[str, Any]:
    sync_control = telegram_sync.get_sync_control_status() if hasattr(telegram_sync, "get_sync_control_status") else {}
    job_state = _telegram_job_runtime_state()
    sync_paused = bool((sync_control or {}).get("paused"))
    worker_connected = bool(
        job_state.get("worker_connected")
        or getattr(telegram_sync, "_started", False)
        or connected
        or getattr(telegram_sync, "_live_handlers_installed", False)
        or getattr(telegram_sync, "entities_by_chat_key", {})
    )
    sync_reading = bool(
        worker_connected
        and (job_state.get("sync_reading") or getattr(telegram_sync, "_live_handlers_installed", False))
    )
    return {
        "telegram_authorized": authorized,
        "worker_connected": worker_connected,
        "sync_paused": sync_paused,
        "sync_pause_reason": (sync_control or {}).get("reason") if sync_paused else None,
        "sync_reading": sync_reading,
        "sync_reading_stage": job_state.get("sync_reading_stage"),
        "sync_status_detail": str(job_state.get("status_detail") or ""),
    }


def _safe_system_metrics_payload(history_points: int = 30) -> dict:
    try:
        return _system_metrics_payload(history_points=history_points)
    except Exception as exc:
        return {
            "ok": False,
            "last_error": str(exc),
            "history": [],
            "tasks": [],
        }


def _append_runtime_log(source: str, message: str) -> None:
    now = _utc_now()
    lines = str(message).splitlines() or [str(message)]
    with _runtime_logs_lock:
        for line in lines:
            safe_line = _mask_pii_text(line) if _runtime_log_mask_pii_enabled() else str(line or "")
            normalized_source = str(source or "").strip().lower()
            normalized_message = safe_line.strip().lower()
            is_telegram = (
                normalized_source in {"telegram", "telegram-sync"}
                or normalized_source.startswith("telegram")
                or "[telegram-sync]" in normalized_message
                or (normalized_message.startswith("[") and "]" in normalized_message)
            )
            _runtime_logs.append(
                {
                    "id": next(_runtime_log_counter),
                    "ts": now.isoformat(),
                    "ts_unix": now.timestamp(),
                    "source": source,
                    "channel": "telegram" if is_telegram else "backend",
                    "error_code": classify_error_text(safe_line),
                    "recovery_hint": recovery_hint(classify_error_text(safe_line)),
                    "message": safe_line,
                }
            )
        _prune_runtime_logs(now)


def _dashboard_function_modes_sync(
    *,
    duckdb_status: Dict[str, Any],
    contacts_status: Any,
    crm_status: Any,
    events_status: Any,
    media_status: Any,
    deals_status: Any,
    import_sync_status: Any,
    dialog_items: List[Any],
    telegram_flood_wait: Dict[str, Any],
    telegram_rate_limits: Dict[str, Any],
) -> List[Dict[str, str]]:
    duckdb_ready = bool(
        duckdb_status.get("cache_ready")
        or duckdb_status.get("indexes_ready")
        or int(duckdb_status.get("message_rows") or 0) > 0
    )
    duckdb_running = bool(duckdb_status.get("running"))
    telegram_sync_control = telegram_sync.get_sync_control_status()
    operation_cooldowns = [
        value
        for value in (telegram_rate_limits.get("operation_cooldowns") or {}).values()
        if isinstance(value, dict) and value.get("active")
    ]
    flood_active = bool((telegram_flood_wait or {}).get("active"))
    telegram_paused = bool((telegram_sync_control or {}).get("paused"))

    rows = [
        _dashboard_mode_row(
            "dashboard",
            "Dashboard",
            "local-snapshot",
            "backend memory + status files",
            "green",
            "Одна лёгкая сводка без обхода всех страниц",
            "Обновляется realtime stream / polling",
        ),
        _dashboard_mode_row(
            "duckdb",
            "Чаты, Sync, сообщения",
            "DuckDB" if duckdb_ready else "local-cache",
            "jsonl -> DuckDB",
            "yellow" if duckdb_running else ("green" if duckdb_ready else "yellow"),
            (
                f"Индексировано {duckdb_status.get('source_files_indexed') or 0} / {duckdb_status.get('source_files_total') or 0}, "
                f"сообщений {duckdb_status.get('message_rows') or 0}"
            ),
            "При повторном добавлении источник продолжает с cursor/state",
        ),
        _analysis_mode_row("contacts", "Контакты", contacts_status, "DuckDB derived cache"),
        _analysis_mode_row("crm", "CRM", crm_status, "DuckDB derived cache + rules"),
        _analysis_mode_row("events", "Мероприятия / календарь", events_status, "DuckDB cache + OpenRouter dates"),
    ]

    media_error = str(_status_attr(media_status, "last_error", "") or "")
    media_running = bool(_status_attr(media_status, "running", False))
    media_rows = int(_status_attr(media_status, "total_rows", 0) or 0)
    media_pending = int(_status_attr(media_status, "pending_count", 0) or 0)
    rows.append(
        _dashboard_mode_row(
            "media",
            "Media / OCR",
            "background-ocr" if media_running else "local-cache",
            "Telegram images + OCR API",
            "red" if media_error else ("yellow" if media_running or media_pending else ("green" if media_rows else "yellow")),
            media_error[:180] if media_error else f"Изображений {media_rows}, ожидает OCR {media_pending}",
            "OCR идёт в фоне и не должен блокировать основную навигацию",
        )
    )

    deals_error = str(_status_attr(deals_status, "last_error", "") or "")
    deals_total = int(_status_attr(deals_status, "total", 0) or 0)
    deals_storage = str(_status_attr(deals_status, "storage", "") or "state.json")
    rows.append(
        _dashboard_mode_row(
            "deals",
            "X-Files сделки",
            "PostgreSQL" if deals_storage == "postgresql" else "local-state",
            deals_storage,
            "red" if deals_error else ("green" if deals_total else "yellow"),
            deals_error[:180] if deals_error else f"Сделок {deals_total}",
            "Сделочный контур открывается из операционного хранилища",
        )
    )

    import_running = bool(_status_attr(import_sync_status, "running", False))
    rows.append(
        _dashboard_mode_row(
            "import",
            "Import",
            "telegram-cache" if dialog_items else "Telegram API",
            "dialogs cache",
            "yellow" if import_running else ("green" if dialog_items else "yellow"),
            f"Диалогов в кеше {len(dialog_items)}",
            "При Telegram cooldown показывается последний кеш",
        )
    )

    if flood_active:
        telegram_tone = "red"
        telegram_status = f"FloodWait до {(telegram_flood_wait or {}).get('can_fetch_after') or (telegram_flood_wait or {}).get('until')}"
        telegram_next = "Telegram-операции на паузе, локальная аналитика продолжает работать"
    elif operation_cooldowns:
        first = operation_cooldowns[0]
        telegram_tone = "yellow"
        telegram_status = f"Cooldown {len(operation_cooldowns)} операций"
        telegram_next = f"Ближайшее возобновление: {first.get('can_fetch_after') or first.get('retry_after')}"
    elif telegram_paused:
        telegram_tone = "yellow"
        telegram_status = f"Sync на паузе: {(telegram_sync_control or {}).get('reason') or 'manual'}"
        telegram_next = "Возобновить можно кнопкой на Dashboard"
    else:
        telegram_tone = "green"
        telegram_status = "Live/backfill доступны"
        telegram_next = "Сканируются только включённые источники"
    rows.append(
        _dashboard_mode_row(
            "telegram",
            "Telegram sync",
            "background-queue",
            "Telethon",
            telegram_tone,
            telegram_status,
            telegram_next,
        )
    )
    rows.append(
        _dashboard_mode_row(
            "openrouter",
            "OpenRouter LLM",
            "background-queue",
            "dates / qualification / routes",
            "yellow" if _status_attr(events_status, "running", False) else "green",
            "Запросы должны запускаться в фоне с progress/log",
            "Результаты повторно читаются из кеша по prompt hash",
        )
    )
    return rows


async def _dashboard_summary_payload(limit: int = 5) -> Dict[str, Any]:
    preview_limit = max(1, min(int(limit or 5), 50))
    duckdb_status = dict(_duckdb_status_snapshot())
    duckdb_status["available"] = bool(duckdb is not None)
    duckdb_status["enabled"] = bool(_DUCKDB_SYNC_ENABLED)
    duckdb_status["db_path"] = str(DUCKDB_PATH)
    source_files_total = len(_duckdb_source_files())
    duckdb_status["source_files_total"] = source_files_total
    duckdb_status["files_on_disk"] = source_files_total
    duckdb_status["files_indexed"] = int(duckdb_status.get("source_files_indexed") or 0)
    duckdb_status["files_with_rows"] = int(duckdb_status.get("source_files_indexed") or 0)
    duckdb_status["next_refresh_at"] = _duckdb_next_refresh_at(duckdb_status.get("last_refresh_at"))
    cached_leads = _lead_snapshot_cache.get("items")
    lead_items = list(cached_leads) if isinstance(cached_leads, list) else []
    lead_preview = _dashboard_preview_model_list(_sort_leads_for_view(lead_items, "recent"), preview_limit)

    cached_dialogs = _telegram_dialogs_cache.get("items")
    dialog_items = list(cached_dialogs) if isinstance(cached_dialogs, list) else []
    dialog_preview = _dashboard_preview_model_list(dialog_items, preview_limit)

    contacts_status = _build_analysis_status("contacts")
    crm_status = _build_analysis_status("crm")
    events_status = _build_analysis_status("events")
    duckdb_counts = {
        # Dashboard must be non-blocking: use already maintained status counters
        # instead of fresh COUNT(*) queries that can wait behind writer locks.
        "leads": int(
            duckdb_status.get("source_files_indexed")
            or duckdb_status.get("tracked_files")
            or duckdb_status.get("source_files_total")
            or len(lead_items)
        ),
        "contacts": int(contacts_status.total_rows or 0),
        "crm": int(crm_status.total_rows or 0),
        "events": int(events_status.total_rows or 0),
    }
    backend_logs = list(reversed(_read_runtime_logs(minutes=60, after_id=0, limit=preview_limit, channel="backend")))
    telegram_logs = list(reversed(_read_runtime_logs(minutes=60, after_id=0, limit=preview_limit, channel="telegram")))
    jsonl_bytes = _sum_glob_file_sizes(PAYME_OUT_DIR, "*.jsonl")
    duckdb_bytes = _safe_file_size(DUCKDB_PATH)
    parquet_bytes = _sum_glob_file_sizes(PARQUET_DIR, "*.parquet")
    parquet_files = _count_glob_files(PARQUET_DIR, "*.parquet")
    media_status = _build_media_status()
    deals_status = _cached_sync_snapshot_fast(
        "xfiles_deals_status",
        _xfiles_deals_status_sync,
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )
    media_images_bytes = int(media_status.images_bytes or 0)
    telegram_flood_wait = telegram_sync.get_global_flood_wait_status()
    telegram_rate_limits = telegram_sync.get_rate_limit_status()
    import_sync_status = _compute_import_sync_status()
    telegram_sync_job_payload = None
    try:
        from app.services import jobs as jobs_service

        if import_sync_status.enabled and import_sync_status.pending_dialogs > 0:
            active_job = jobs_service.latest_active_job_by_type("telegram_sync")
            if active_job is None or jobs_service.is_stale_telegram_sync_job(active_job):
                jobs_service.ensure_telegram_sync_job(reason="dashboard-auto-recover")

        telegram_sync_job = (
            jobs_service.latest_active_job_by_type("telegram_sync")
            or jobs_service.latest_job_by_type("telegram_sync")
        )
        telegram_sync_job_payload = (
            telegram_sync_job.model_dump()
            if hasattr(telegram_sync_job, "model_dump")
            else telegram_sync_job
        )
    except Exception:
        telegram_sync_job_payload = None
    selected_source_identities: Set[str] = set()
    for selector in _source_selectors_as_strings():
        identity = _selector_identity(selector)
        if identity:
            selected_source_identities.add(identity)
    selected_source_count = len(selected_source_identities)
    license_status = _xfiles_license_status_payload()
    update_status = _xfiles_update_status_payload()
    function_modes = _dashboard_function_modes_sync(
        duckdb_status=duckdb_status,
        contacts_status=contacts_status,
        crm_status=crm_status,
        events_status=events_status,
        media_status=media_status,
        deals_status=deals_status,
        import_sync_status=import_sync_status,
        dialog_items=dialog_items,
        telegram_flood_wait=telegram_flood_wait,
        telegram_rate_limits=telegram_rate_limits,
    )
    scanned_sources = build_dashboard_scanned_sources_payload(
        lead_items=lead_items,
        dialog_items=dialog_items,
        telegram_flood_wait=telegram_flood_wait,
        telegram_rate_limits=telegram_rate_limits,
        limit=max(preview_limit, selected_source_count),
        source_selectors=_source_selectors_as_strings(),
        import_sync_selectors=telegram_sync.get_import_sync_selectors(),
        telegram_sync=telegram_sync,
        selector_to_lead_name=_selector_to_lead_name,
        lead_scan_group_fields=_lead_scan_group_fields,
        telegram_chat_state_for_lead=_telegram_chat_state_for_lead,
        utc_now=_utc_now,
    )
    active_telegram_sources: list[dict[str, Any]] = []
    try:
        job_status = str((telegram_sync_job_payload or {}).get("status") or "").lower()
        if job_status in {"running", "queued", "pending"}:
            job_result = (telegram_sync_job_payload or {}).get("result") or {}
            raw_active_sources = job_result.get("active_sources") if isinstance(job_result, dict) else []
            if isinstance(raw_active_sources, list):
                active_telegram_sources = [
                    item
                    for item in raw_active_sources
                    if isinstance(item, dict) and str(item.get("selector") or item.get("title") or "").strip()
                ][:50]
            totals = scanned_sources.setdefault("totals", {})
            worker_done = max(0, int((telegram_sync_job_payload or {}).get("chunks_done") or 0))
            raw_worker_total = max(0, int((telegram_sync_job_payload or {}).get("chunks_total") or selected_source_count or 0))
            worker_total = (
                min(raw_worker_total, selected_source_count)
                if selected_source_count > 0 and raw_worker_total > selected_source_count
                else raw_worker_total
            )
            worker_active = max(len(active_telegram_sources), int(totals.get("active_sources") or 0))
            worker_pending = (
                max(0, worker_total - max(worker_done, worker_active))
                if worker_total
                else int(totals.get("pending_sources") or 0)
            )
            totals["active_sources"] = worker_active
            totals["pending_sources"] = worker_pending
            totals["selected_sources"] = max(int(totals.get("selected_sources") or 0), worker_total, selected_source_count)
            if active_telegram_sources:
                active_identities = {
                    str(item.get("selector") or item.get("title") or "").strip().lower()
                    for item in active_telegram_sources
                }
                for row in scanned_sources.get("items") or []:
                    row_keys = {
                        str(row.get("selector") or "").strip().lower(),
                        str(row.get("source") or "").strip().lower(),
                        str(row.get("title") or "").strip().lower(),
                    }
                    if active_identities.intersection(row_keys):
                        row["status"] = "active"
                        row["status_label"] = "worker читает Telegram"
                        row["tone"] = "green"
                        row["telegram_active"] = True
                scanned_sources["items"] = sorted(
                    scanned_sources.get("items") or [],
                    key=lambda item: (
                        0 if item.get("status") == "active" else 1,
                        -float(item.get("read_progress_percent") or 0.0),
                        -int(item.get("messages_count") or 0),
                        str(item.get("title") or item.get("source") or ""),
                    ),
                )
            scanned_sources["message"] = (
                f"Telegram worker сканирует: подключено {worker_done}/{worker_total}; "
                f"активно {worker_active}, ожидают {worker_pending}, "
                f"сообщений {int(totals.get('messages_count') or 0)}"
            )
    except Exception as exc:
        _append_runtime_log("dashboard", f"Dashboard scanned_sources merge failed: {exc}")

    return {
        "ts": _utc_now().isoformat(),
        "counts": {
            "leads": int(duckdb_counts.get("leads") or len(lead_items)),
            "dialogs": len(dialog_items),
            "contacts": int(duckdb_counts.get("contacts") or contacts_status.total_rows or 0),
            "crm": int(duckdb_counts.get("crm") or crm_status.total_rows or 0),
            "events": int(duckdb_counts.get("events") or events_status.total_rows or 0),
            "images": int(media_status.total_rows or 0),
            "ocr_processed": int(media_status.processed_count or 0),
            "ocr_pending": int(media_status.pending_count or 0),
            "ocr_crm_rows": int(media_status.crm_rows_created or 0),
            "ocr_deleted_images": int(media_status.deleted_images or 0),
            "deals": int(deals_status.total or 0),
            "active_deals": int(deals_status.active or 0),
            "won_deals": int(deals_status.won or 0),
            "lost_deals": int(deals_status.lost or 0),
            "expected_deal_profit": float(deals_status.expected_profit or 0.0),
            "pipeline_value": float(deals_status.pipeline_value or 0.0),
            "pipeline_profit": float(deals_status.pipeline_profit or 0.0),
            "pipeline_profit_per_attention_hour": float(deals_status.pipeline_profit_per_attention_hour or 0.0),
            "qualified_leads_today": int(deals_status.qualified_leads_today or 0),
            "new_deal_signals_today": int(deals_status.new_signals_today or 0),
            "overdue_deal_actions": int(deals_status.stale_actions or deals_status.overdue or 0),
            "runtime_logs": len(backend_logs) + len(telegram_logs),
            "backend_logs": len(backend_logs),
            "telegram_logs": len(telegram_logs),
            "selected_sources": selected_source_count,
        },
        "storage": {
            "jsonl_bytes": jsonl_bytes,
            "duckdb_bytes": duckdb_bytes,
            "parquet_bytes": parquet_bytes,
            "parquet_files": parquet_files,
            "media_images_bytes": media_images_bytes,
        },
        "previews": {
            "leads": lead_preview,
            "dialogs": dialog_preview,
            "contacts": [],
            "crm": [],
            "events": [],
            "images": [],
            "runtime_logs": [*backend_logs, *telegram_logs][:preview_limit],
            "backend_logs": backend_logs,
            "telegram_logs": telegram_logs,
        },
        "runtime": (await _runtime_status()).model_dump(),
        "server": ServerRuntimeDTO(**_server_runtime_snapshot()).model_dump(),
        "system": _safe_system_metrics_payload(history_points=30),
        "telegram": {
            "flood_wait": telegram_flood_wait,
            "rate_limits": telegram_rate_limits,
            "sync_control": telegram_sync.get_sync_control_status(),
            "selected_sources": selected_source_count,
            "source_count": selected_source_count,
        },
        "scanned_sources": scanned_sources,
        "active_telegram_sources": active_telegram_sources,
        "telegram_flood_wait": telegram_flood_wait,
        "telegram_rate_limits": telegram_rate_limits,
        "telegram_sync_control": telegram_sync.get_sync_control_status(),
        "telegram_sync_job": telegram_sync_job_payload,
        "duckdb_sync": duckdb_status,
        "license": license_status,
        "update": update_status,
        "xfiles": {
            "project": PROJECT_NAME,
            "subtitle": PROJECT_SUBTITLE,
            "deals": deals_status.model_dump(),
            "license": license_status,
            "update": update_status,
        },
        "deals": deals_status.model_dump(),
        "crm": crm_status.model_dump(),
        "events": events_status.model_dump(),
        "contacts": contacts_status.model_dump(),
        "duckdb": duckdb_status,
        "media": media_status.model_dump(),
        "import_sync": import_sync_status.model_dump(),
        "function_modes": function_modes,
    }


def _collect_system_metrics_snapshot() -> Dict[str, Any]:
    now = _utc_now()
    cpu_count = max(1, int(os.cpu_count() or 1))
    load_avg: List[float] = []
    try:
        load_avg = [_round_metric(value, 2) for value in os.getloadavg()]
    except Exception:
        load_avg = [0.0, 0.0, 0.0]

    if psutil is not None:
        try:
            cpu_percent = float(psutil.cpu_percent(interval=None))
        except Exception:
            cpu_percent = min(100.0, (load_avg[0] / cpu_count) * 100.0) if load_avg else 0.0
        try:
            vm = psutil.virtual_memory()
            memory_used_mb = float(vm.used) / (1024 * 1024)
            memory_total_mb = float(vm.total) / (1024 * 1024)
            memory_percent = float(vm.percent)
        except Exception:
            memory_used_mb, memory_total_mb, memory_percent = _fallback_memory_snapshot()
        try:
            process_memory_mb = float(_psutil_process.memory_info().rss) / (1024 * 1024) if _psutil_process else 0.0
        except Exception:
            process_memory_mb = _process_memory_mb_fallback()
        try:
            process_cpu_percent = float(_psutil_process.cpu_percent(interval=None)) if _psutil_process else 0.0
        except Exception:
            process_cpu_percent = _process_cpu_percent_fallback()
    else:
        cpu_percent = min(100.0, (load_avg[0] / cpu_count) * 100.0) if load_avg else 0.0
        memory_used_mb, memory_total_mb, memory_percent = _fallback_memory_snapshot()
        process_memory_mb = _process_memory_mb_fallback()
        process_cpu_percent = _process_cpu_percent_fallback()

    disk_usage = shutil.disk_usage(APP_DIR)
    disk_total_gb = float(disk_usage.total) / (1024 ** 3)
    disk_free_gb = float(disk_usage.free) / (1024 ** 3)
    disk_used_gb = max(0.0, disk_total_gb - disk_free_gb)

    return {
        "ts": now.isoformat(),
        "sampler_interval_sec": _SYSTEM_METRICS_INTERVAL_SEC,
        "cpu_count": cpu_count,
        "cpu_percent": _round_metric(cpu_percent),
        "load_avg": load_avg,
        "memory_used_mb": _round_metric(memory_used_mb),
        "memory_total_mb": _round_metric(memory_total_mb),
        "memory_percent": _round_metric(memory_percent),
        "disk_used_gb": _round_metric(disk_used_gb),
        "disk_free_gb": _round_metric(disk_free_gb),
        "disk_total_gb": _round_metric(disk_total_gb),
        "process_cpu_percent": _round_metric(process_cpu_percent),
        "process_memory_mb": _round_metric(process_memory_mb),
        "open_files": _safe_open_files_count(),
        "threads": _safe_thread_count(),
    }


def _background_task_statuses() -> List["BackgroundTaskStatusDTO"]:
    rows: List["BackgroundTaskStatusDTO"] = []
    labels = {
        "crm": "CRM",
        "events": "Мероприятия",
        "contacts": "Контакты",
    }
    for kind in _ANALYSIS_KINDS:
        status = _build_analysis_status(kind)
        task_status: Literal["idle", "running", "error", "disabled", "stale"] = "idle"
        if not status.enabled:
            task_status = "disabled"
        elif status.running:
            task_status = "running"
        elif status.last_error:
            task_status = "error"
        elif status.stale_reason:
            task_status = "stale"
        summary = (
            f"{status.progress_current} / {status.progress_total}"
            if status.running and status.progress_total > 0
            else f"Кеш строк: {status.total_rows}"
        )
        if status.stale_reason and not status.running:
            summary = status.stale_reason
        rows.append(
            BackgroundTaskStatusDTO(
                kind=kind,
                label=labels.get(kind, kind.upper()),
                status=task_status,
                running=status.running,
                enabled=status.enabled,
                cache_ready=status.cache_ready,
                total_rows=status.total_rows,
                progress_current=status.progress_current,
                progress_total=status.progress_total,
                progress_percent=status.progress_percent,
                current_item=status.current_item,
                summary=summary,
                last_refresh_at=status.last_refresh_at,
                next_refresh_at=status.next_refresh_at,
                last_error=status.last_error,
            )
        )

    duckdb_status = _build_duckdb_status()
    duckdb_task_status: Literal["idle", "running", "error", "disabled", "stale"] = "disabled"
    if duckdb_status.running:
        duckdb_task_status = "running"
    elif not duckdb_status.available or not duckdb_status.enabled:
        duckdb_task_status = "disabled"
    elif duckdb_status.last_error:
        duckdb_task_status = "error"
    elif duckdb_status.stale_reason:
        duckdb_task_status = "stale"
    else:
        duckdb_task_status = "idle"
    duckdb_summary = (
        f"Файлов {duckdb_status.source_files_indexed} / {duckdb_status.source_files_total}, сообщений {duckdb_status.message_rows}"
    )
    if duckdb_status.stale_reason and not duckdb_status.running:
        duckdb_summary = duckdb_status.stale_reason
    rows.append(
        BackgroundTaskStatusDTO(
            kind="duckdb",
            label="DuckDB",
            status=duckdb_task_status,
            running=duckdb_status.running,
            enabled=duckdb_status.enabled and duckdb_status.available,
            cache_ready=duckdb_status.cache_ready,
            total_rows=duckdb_status.message_rows,
            progress_current=duckdb_status.progress_current,
            progress_total=duckdb_status.progress_total,
            progress_percent=duckdb_status.progress_percent,
            current_item=duckdb_status.current_item,
            summary=duckdb_summary,
            last_refresh_at=duckdb_status.last_refresh_at,
            next_refresh_at=duckdb_status.next_refresh_at,
            last_error=duckdb_status.last_error,
        )
    )

    event_date_snapshot_fn = globals().get("_event_date_status_snapshot")
    if callable(event_date_snapshot_fn):
        try:
            event_date_status = event_date_snapshot_fn()
            event_last_error = str(event_date_status.get("last_error") or "").strip() or None
            event_running = bool(event_date_status.get("running", False))
            event_task_status: Literal["idle", "running", "error", "disabled", "stale"] = "running" if event_running else "idle"
            if event_last_error and not event_running:
                event_task_status = "error"
            rows.append(
                BackgroundTaskStatusDTO(
                    kind="openrouter_event_dates",
                    label="OpenRouter даты событий",
                    status=event_task_status,
                    running=event_running,
                    enabled=True,
                    cache_ready=int(event_date_status.get("total", 0) or 0) > 0,
                    total_rows=int(event_date_status.get("total", 0) or 0),
                    progress_current=int(event_date_status.get("processed", 0) or 0),
                    progress_total=int(event_date_status.get("total", 0) or 0),
                    progress_percent=float(event_date_status.get("percent", 0.0) or 0.0),
                    current_item=None,
                    summary=(
                        f"Дат найдено: {int(event_date_status.get('found', 0) or 0)}, "
                        f"осталось: {int(event_date_status.get('pending', 0) or 0)}, "
                        f"скорость: {float(event_date_status.get('rate_per_min', 0.0) or 0.0):.1f}/мин"
                    ),
                    last_refresh_at=event_date_status.get("updated_at"),
                    next_refresh_at=None,
                    last_error=event_last_error,
                )
            )
        except Exception as exc:
            rows.append(
                BackgroundTaskStatusDTO(
                    kind="openrouter_event_dates",
                    label="OpenRouter даты событий",
                    status="error",
                    running=False,
                    enabled=True,
                    cache_ready=False,
                    summary="Не удалось прочитать статус LLM-дат",
                    last_error=str(exc),
                )
            )

    xfiles_snapshot_fn = globals().get("_xfiles_deal_cache_status_snapshot")
    if callable(xfiles_snapshot_fn):
        xfiles_cache_status = xfiles_snapshot_fn()
        status_cache = _api_snapshot_cache_peek("xfiles_deals_status")
        xfiles_last_error = str(xfiles_cache_status.get("last_error") or "").strip() or None
        xfiles_running = bool(xfiles_cache_status.get("running", False))
        xfiles_task_status: Literal["idle", "running", "error", "disabled", "stale"] = "running" if xfiles_running else "idle"
        if xfiles_last_error and not xfiles_running:
            xfiles_task_status = "error"
        xfiles_total_rows = 0
        if status_cache and isinstance(status_cache.get("value"), XFilesDealsStatusDTO):
            xfiles_total_rows = int(status_cache["value"].total or 0)
        rows.append(
            BackgroundTaskStatusDTO(
                kind="xfiles_deal_cache",
                label="X-Files кеш сделок",
                status=xfiles_task_status,
                running=xfiles_running,
                enabled=_XFILES_DEAL_CACHE_WARMUP_ENABLED,
                cache_ready=status_cache is not None,
                total_rows=xfiles_total_rows,
                progress_current=int(xfiles_cache_status.get("progress_current", 0) or 0),
                progress_total=int(xfiles_cache_status.get("progress_total", 0) or 0),
                progress_percent=float(xfiles_cache_status.get("progress_percent", 0.0) or 0.0),
                current_item=xfiles_cache_status.get("current_item"),
                summary=(
                    f"Прогрев: {xfiles_cache_status.get('progress_current', 0)} / "
                    f"{xfiles_cache_status.get('progress_total', 0)}"
                    if xfiles_running
                    else "Кеш готов" if status_cache is not None else "Ожидает первого прогрева"
                ),
                last_refresh_at=xfiles_cache_status.get("updated_at") or xfiles_cache_status.get("finished_at"),
                next_refresh_at=None,
                last_error=xfiles_last_error,
            )
        )

    import_status = _compute_import_sync_status()
    import_task_status: Literal["idle", "running", "error", "disabled", "stale"] = "disabled"
    if import_status.enabled and import_status.pending_dialogs > 0:
        import_task_status = "running"
    elif import_status.enabled:
        import_task_status = "idle"
    rows.append(
        BackgroundTaskStatusDTO(
            kind="import",
            label="Импорт",
            status=import_task_status,
            running=import_task_status == "running",
            enabled=import_status.enabled,
            cache_ready=import_status.total_dialogs > 0,
            total_rows=import_status.total_dialogs,
            progress_current=import_status.completed_dialogs,
            progress_total=import_status.total_dialogs,
            progress_percent=import_status.progress_percent,
            current_item=None,
            summary=import_status.message,
            last_refresh_at=import_status.updated_at,
            next_refresh_at=None,
            last_error=None,
        )
    )

    try:
        from app.services import jobs as jobs_service

        telegram_job = jobs_service.latest_job_by_type("telegram_sync")
        if telegram_job is not None:
            telegram_status_raw = str(telegram_job.status or "idle")
            telegram_task_status: Literal["idle", "running", "error", "disabled", "stale"] = "idle"
            if telegram_status_raw in {"running", "queued", "pending"}:
                telegram_task_status = "running"
            elif telegram_status_raw in {"failed", "error"}:
                telegram_task_status = "error"
            elif telegram_status_raw == "cancelled":
                telegram_task_status = "stale"
            rows.append(
                BackgroundTaskStatusDTO(
                    kind="telegram_sync_worker",
                    label="Telegram worker",
                    status=telegram_task_status,
                    running=telegram_task_status == "running",
                    enabled=True,
                    cache_ready=telegram_job.status not in {"idle", "failed", "error"},
                    total_rows=int(telegram_job.chunks_total or 0),
                    progress_current=int(telegram_job.chunks_done or 0),
                    progress_total=int(telegram_job.chunks_total or 0),
                    progress_percent=float(telegram_job.progress_percent or 0.0),
                    current_item=None,
                    summary=telegram_job.progress_label or f"Job {telegram_job.status}",
                    last_refresh_at=telegram_job.updated_at,
                    next_refresh_at=None,
                    last_error=telegram_job.error,
                )
            )
    except Exception as exc:
        rows.append(
            BackgroundTaskStatusDTO(
                kind="telegram_sync_worker",
                label="Telegram worker",
                status="error",
                running=False,
                enabled=True,
                cache_ready=False,
                summary="Не удалось прочитать durable Telegram sync job",
                last_error=str(exc),
            )
        )

    ocr_enabled = _ocr_is_enabled()
    ocr_running = bool(_image_ocr_status.get("running", False))
    ocr_error = str(_image_ocr_status.get("last_error") or "").strip() or None
    ocr_status: Literal["idle", "running", "error", "disabled", "stale"] = "disabled"
    if ocr_running:
        ocr_status = "running"
    elif not ocr_enabled:
        ocr_status = "disabled"
    elif ocr_error:
        ocr_status = "error"
    else:
        ocr_status = "idle"
    rows.append(
        BackgroundTaskStatusDTO(
            kind="ocr",
            label="OCR",
            status=ocr_status,
            running=ocr_running,
            enabled=ocr_enabled,
            cache_ready=bool(_image_ocr_status.get("available", False)),
            total_rows=int(_image_ocr_status.get("processed_count", 0) or 0),
            progress_current=int(_image_ocr_status.get("processed_count", 0) or 0),
            progress_total=int(_image_ocr_status.get("processed_count", 0) or 0),
            progress_percent=100.0 if not ocr_running and ocr_enabled else 0.0,
            current_item=None,
            summary=f"Обработано: {int(_image_ocr_status.get('processed_count', 0) or 0)}, ошибок: {int(_image_ocr_status.get('error_count', 0) or 0)}",
            last_refresh_at=_image_ocr_status.get("last_finished_at"),
            next_refresh_at=None,
            last_error=ocr_error,
        )
    )
    return rows


async def _runtime_status() -> RuntimeStatusDTO:
    global _tg_bootstrap_task
    session_file_exists = _telegram_session_file_path().exists()
    settings = _get_app_settings()
    client_delivery_first_start = bool(
        _xfiles_client_delivery_mode() and settings.get("first_start_wizard_required")
    )
    manual_telegram_auth_started = bool(
        str(settings.get("telegram_phone") or "").strip()
        or telegram_sync._auth_step in {"code", "password", "done"}
    )
    # Client ZIPs must not inherit or auto-advertise any development Telegram session.
    if client_delivery_first_start and not manual_telegram_auth_started:
        session_file_exists = False
    api_configured = bool(settings.get("telegram_api_configured"))
    api_runtime_fields = {
        "telegram_api_configured": api_configured,
        "telegram_api_id": settings.get("telegram_api_id") or None,
        "telegram_api_credentials_source": str(settings.get("telegram_api_credentials_source") or ""),
    }
    auth_code_fields = telegram_sync.auth_code_status() if hasattr(telegram_sync, "auth_code_status") else {}
    connected = bool(telegram_sync.client and telegram_sync.client.is_connected())
    if client_delivery_first_start and not manual_telegram_auth_started:
        connected = False
    authorized: Optional[bool] = None
    status_flags = _runtime_status_telegram_flags(connected=connected, authorized=authorized)

    if not api_configured or not telegram_sync.has_api_credentials():
        telegram_sync._auth_step = "api"
        telegram_sync._auth_last_error = telegram_sync._auth_last_error or None
        return RuntimeStatusDTO(
            auth_status="needs_api_credentials",
            auth_message="Укажите Telegram api_id и api_hash из my.telegram.org → API development tools.",
            session_file_exists=session_file_exists,
            connected=connected,
            auth_step="api",
            pending_phone=telegram_sync._auth_phone,
            last_error=telegram_sync._auth_last_error,
            **status_flags,
            **auth_code_fields,
            **api_runtime_fields,
        )

    if (
        _RUNTIME_STATUS_TELEGRAM_AUTOSTART_ENABLED
        and session_file_exists
        and not connected
        and telegram_sync._auth_step not in {"code", "password"}
    ):
        if _tg_bootstrap_task is None or _tg_bootstrap_task.done():
            _tg_bootstrap_task = asyncio.create_task(telegram_sync.start(sync_in_background=True))

    if connected:
        try:
            authorized = await asyncio.wait_for(
                telegram_sync.client.is_user_authorized(),
                timeout=_RUNTIME_STATUS_TELEGRAM_AUTH_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            authorized = None
        except AuthKeyUnregisteredError:
            authorized = False
        except Exception:
            authorized = None
    status_flags = _runtime_status_telegram_flags(connected=connected, authorized=authorized)

    if (
        not (client_delivery_first_start and not manual_telegram_auth_started)
        and (authorized is True or telegram_sync._live_handlers_installed or telegram_sync.entities_by_chat_key)
    ):
        telegram_sync._auth_step = "done"
        telegram_sync._auth_last_error = None
        return RuntimeStatusDTO(
            auth_status="authorized",
            auth_message="Telegram уже авторизован",
            session_file_exists=session_file_exists,
            connected=connected,
            auth_step="done",
            pending_phone=telegram_sync._auth_phone,
            last_error=None,
            **status_flags,
            **auth_code_fields,
            **api_runtime_fields,
        )

    if authorized is False or not session_file_exists:
        auth_step = telegram_sync._auth_step if telegram_sync._auth_step in {"code", "password"} else "phone"
        if auth_step == "code":
            auth_message = "Введите код из Telegram"
        elif auth_step == "password":
            auth_message = "Введите пароль двухфакторной защиты"
        else:
            auth_message = "Нужна авторизация Telegram в интерфейсе"
        return RuntimeStatusDTO(
            auth_status="needs_auth",
            auth_message=auth_message,
            session_file_exists=session_file_exists,
            connected=connected,
            auth_step=auth_step,
            pending_phone=telegram_sync._auth_phone,
            last_error=telegram_sync._auth_last_error,
            **status_flags,
            **auth_code_fields,
            **api_runtime_fields,
        )

    if session_file_exists:
        return RuntimeStatusDTO(
            auth_status="session_present",
            auth_message="Найдена сохраненная сессия Telegram. Пробуем подключиться автоматически без повторной авторизации.",
            session_file_exists=session_file_exists,
            connected=connected,
            auth_step=telegram_sync._auth_step if telegram_sync._auth_step in {"code", "password"} else "phone",
            pending_phone=telegram_sync._auth_phone,
            last_error=telegram_sync._auth_last_error,
            **status_flags,
            **auth_code_fields,
            **api_runtime_fields,
        )

    return RuntimeStatusDTO(
        auth_status="unknown",
        auth_message="Статус авторизации пока не определён",
        session_file_exists=session_file_exists,
        connected=connected,
        auth_step=telegram_sync._auth_step if telegram_sync._auth_step in {"code", "password"} else "phone",
        pending_phone=telegram_sync._auth_phone,
        last_error=telegram_sync._auth_last_error,
        **status_flags,
        **auth_code_fields,
        **api_runtime_fields,
    )


__all__ = [
    "refresh_legacy_globals",
    "_append_runtime_log",
    "_background_task_statuses",
    "_collect_system_metrics_snapshot",
    "_dashboard_function_modes_sync",
    "_dashboard_summary_payload",
    "_runtime_status",
]
