"""FastAPI startup/shutdown registration for the legacy-compatible runtime."""

from __future__ import annotations

import asyncio
from typing import Any, Dict


async def _cancel_runtime_task(runtime: Dict[str, Any], name: str) -> None:
    task = runtime.get(name)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if name in {"_duckdb_sync_task"}:
        runtime[name] = None


def register_runtime_lifespan(app: Any, runtime: Dict[str, Any]) -> None:
    @app.on_event("startup")
    async def _tg_start() -> None:
        runtime["_startup_status_update"]("server", 10, "FastAPI startup начат")
        snapshot = runtime["_server_runtime_snapshot"]()
        runtime["_append_runtime_log"](
            "server",
            f"startup: mode={snapshot['mode']} pid={snapshot['pid']} host={snapshot['hostname']} instance={snapshot['instance_id']}",
        )
        await asyncio.to_thread(runtime["_record_system_metrics_snapshot"])
        runtime["_startup_status_update"]("system_metrics", 20, "Снят первый snapshot системных метрик")
        deleted_non_images = runtime["_delete_non_image_media_files"]()
        if deleted_non_images:
            print(f"[media] deleted stray non-image media files: {deleted_non_images}")
        runtime["_startup_status_update"]("state", 32, "Загружаю state и настройки Telegram API")
        telegram_sync = runtime["telegram_sync"]
        telegram_sync.state = telegram_sync.load_state()
        api_id, api_hash = runtime["_resolve_telegram_api_credentials"](runtime["_get_app_settings"]())
        await telegram_sync.apply_api_credentials(api_id, api_hash)

        runtime["_startup_status_update"]("background_tasks", 48, "Восстанавливаю фоновые задачи и кеши")
        runtime["_reset_stale_analysis_running_flags"]()
        if runtime["_xfiles_is_menu_allowed"]("deals"):
            runtime["_xfiles_schedule_deal_cache_warmup"]("startup")
        bootstrap_task = runtime.get("_tg_bootstrap_task")
        if runtime["_STARTUP_TELEGRAM_BOOTSTRAP_ENABLED"] and (bootstrap_task is None or bootstrap_task.done()):
            runtime["_tg_bootstrap_task"] = asyncio.create_task(runtime["_bootstrap_telegram_sync"]())
        if runtime["_STARTUP_OCR_SWEEP_ENABLED"] and runtime["_xfiles_is_menu_allowed"]("media"):
            runtime["_ensure_pending_image_ocr_task"](force=False)
        media_loop_task = runtime.get("_media_ocr_loop_task")
        if runtime["_xfiles_is_menu_allowed"]("media") and (media_loop_task is None or media_loop_task.done()):
            runtime["_media_ocr_loop_task"] = asyncio.create_task(runtime["_media_ocr_background_loop"]())
        analysis_task = runtime.get("_analysis_autorefresh_task")
        if runtime["_STARTUP_ANALYSIS_AUTOREFRESH_ENABLED"] and (analysis_task is None or analysis_task.done()):
            runtime["_analysis_autorefresh_task"] = asyncio.create_task(runtime["_analysis_autorefresh_loop"]())

        runtime["_startup_status_update"]("duckdb", 68, "Проверяю DuckDB и локальные аналитические индексы")
        if runtime.get("duckdb") is not None and runtime["_DUCKDB_SYNC_ENABLED"]:
            try:
                await asyncio.to_thread(runtime["_duckdb_init_schema_sync"])
                runtime["_duckdb_bootstrap_status_from_existing_db"]()
                runtime["_duckdb_update_status"](
                    available=True,
                    enabled=True,
                    db_path=str(runtime["DUCKDB_PATH"]),
                    last_error=None,
                )
                if runtime["_STARTUP_DUCKDB_SYNC_ENABLED"]:
                    runtime["_schedule_duckdb_sync"](force_full=False)
            except Exception as exc:
                runtime["_duckdb_update_status"](
                    available=True,
                    enabled=True,
                    last_error=str(exc),
                    stale_reason="DuckDB не смог инициализировать локальную базу",
                )
                runtime["_append_runtime_log"]("duckdb", f"startup init failed: {exc}")
            duckdb_autorefresh_task = runtime.get("_duckdb_autorefresh_task")
            if runtime["_STARTUP_DUCKDB_AUTOREFRESH_ENABLED"] and (
                duckdb_autorefresh_task is None or duckdb_autorefresh_task.done()
            ):
                runtime["_duckdb_autorefresh_task"] = asyncio.create_task(runtime["_duckdb_autorefresh_loop"]())
        else:
            runtime["_duckdb_update_status"](
                available=runtime.get("duckdb") is not None,
                enabled=runtime["_DUCKDB_SYNC_ENABLED"],
                stale_reason="DuckDB отключён или зависимость не установлена",
            )

        runtime["_startup_status_update"]("runtime_loops", 92, "Запускаю runtime loops и realtime-мониторинг")
        system_metrics_task = runtime.get("_system_metrics_task")
        if system_metrics_task is None or system_metrics_task.done():
            runtime["_system_metrics_task"] = asyncio.create_task(runtime["_system_metrics_loop"]())
        runtime["_append_runtime_log"](
            "server",
            "startup complete"
            f" | telegram_bootstrap={'on' if runtime['_STARTUP_TELEGRAM_BOOTSTRAP_ENABLED'] else 'off'}"
            f" | analysis_autorefresh={'on' if runtime['_STARTUP_ANALYSIS_AUTOREFRESH_ENABLED'] else 'off'}"
            f" | duckdb_sync={'on' if runtime['_STARTUP_DUCKDB_SYNC_ENABLED'] else 'off'}"
            f" | duckdb_autorefresh={'on' if runtime['_STARTUP_DUCKDB_AUTOREFRESH_ENABLED'] else 'off'}"
            f" | ocr_sweep={'on' if runtime['_STARTUP_OCR_SWEEP_ENABLED'] else 'off'}",
        )
        runtime["_startup_status_update"]("complete", 100, "Backend startup complete", complete=True)

    @app.on_event("shutdown")
    async def _tg_stop() -> None:
        runtime["_append_runtime_log"]("server", "shutdown requested")
        for task_name in (
            "_tg_bootstrap_task",
            "_analysis_autorefresh_task",
            "_media_ocr_loop_task",
            "_duckdb_autorefresh_task",
            "_system_metrics_task",
            "_duckdb_sync_task",
        ):
            await _cancel_runtime_task(runtime, task_name)

        analysis_refresh_tasks = runtime.get("_analysis_refresh_tasks") or {}
        for kind, task in list(analysis_refresh_tasks.items()):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            analysis_refresh_tasks[kind] = None

        await _cancel_runtime_task(runtime, "_image_ocr_task")
        try:
            await runtime["telegram_sync"].stop()
        except Exception as exc:
            print(f"[telegram-sync] shutdown failed: {exc!r}")
        runtime["_append_runtime_log"]("server", "shutdown complete")
