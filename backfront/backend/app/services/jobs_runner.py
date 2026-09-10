"""Worker runner for durable jobs."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from app.schemas.jobs import JobProgressDTO


def _load_telegram_sync_for_worker():
    """Initialize TelegramSync in Celery with the same legacy config as FastAPI."""
    import app.legacy_runtime  # noqa: F401
    from app.core.app_settings import _get_app_settings
    from app.services import telegram_sync_runtime

    telegram_sync_runtime.refresh_legacy_globals()
    sync = telegram_sync_runtime.telegram_sync
    settings = _get_app_settings()
    api_id = getattr(telegram_sync_runtime, "API_ID", None) or settings.get("telegram_api_id")
    api_hash = getattr(telegram_sync_runtime, "API_HASH", None) or settings.get("telegram_api_hash")
    if api_id is not None and api_id != "":
        try:
            api_id = int(api_id)
        except Exception:
            pass
    if sync is None or not sync.has_api_credentials():
        required = ("SESSION", "PAYME_OUT_DIR", "STATE_PATH")
        missing = [name for name in required if name not in telegram_sync_runtime.__dict__]
        if not api_id:
            missing.append("telegram_api_id")
        if not api_hash:
            missing.append("telegram_api_hash")
        if missing:
            raise RuntimeError(f"Telegram runtime config is missing in worker: {', '.join(missing)}")
        sync = telegram_sync_runtime.TelegramSync(
            api_id=api_id,
            api_hash=str(api_hash),
            session=telegram_sync_runtime.SESSION,
            out_dir=telegram_sync_runtime.PAYME_OUT_DIR,
            state_path=telegram_sync_runtime.STATE_PATH,
        )
        telegram_sync_runtime.telegram_sync = sync
    return sync


def run_simulated_job(
    job_id: str,
    *,
    get_job: Callable[[str], JobProgressDTO],
    update_job: Callable[..., JobProgressDTO],
    record_event: Callable[..., object],
    utc_now_iso: Callable[[], str],
) -> JobProgressDTO:
    job = update_job(job_id, status="running", progress_percent=3, progress_label="Worker взял задачу", attempts_delta=1)
    steps = max(1, min(20, int(job.payload.get("simulation_steps") or 5)))
    sleep_sec = max(0.0, min(5.0, float(job.payload.get("simulation_step_sec") or 0.2)))
    for index in range(steps):
        current = get_job(job_id)
        if current.status == "cancelled":
            record_event(job_id, "Worker остановлен: задача отменена", level="warning")
            return current
        done = index + 1
        percent = min(95.0, 5.0 + (done / steps) * 85.0)
        eta = max(0.0, (steps - done) * sleep_sec)
        update_job(
            job_id,
            status="running",
            progress_percent=percent,
            progress_label=f"Обработан chunk {done}/{steps}",
            eta_seconds=eta,
            chunks_done=done,
            chunks_total=steps,
        )
        if sleep_sec:
            time.sleep(sleep_sec)
    result = {
        "ok": True,
        "type": job.type,
        "message": "Фоновая задача выполнена worker-ом",
        "completed_at": utc_now_iso(),
    }
    return update_job(job_id, status="done", progress_percent=100, progress_label="Задача завершена", eta_seconds=0, result=result)


def run_telegram_sync_job(
    job_id: str,
    *,
    get_job: Callable[[str], JobProgressDTO],
    update_job: Callable[..., JobProgressDTO],
    record_event: Callable[..., object],
    utc_now_iso: Callable[[], str],
) -> JobProgressDTO:
    """Own Telegram live-sync from the telegram Celery worker, not from FastAPI."""

    async def _runner() -> JobProgressDTO:
        telegram_sync = _load_telegram_sync_for_worker()

        def _task_sources(task_map: object, stage: str) -> list[dict[str, str | None]]:
            rows: list[dict[str, str | None]] = []
            if not isinstance(task_map, dict):
                return rows
            for key, task in task_map.items():
                try:
                    is_running = bool(task and not task.done())
                except Exception:
                    is_running = False
                if not is_running:
                    continue
                value = str(key or "").strip()
                if not value:
                    continue
                chat_state = {}
                try:
                    chat_state = telegram_sync.get_chat_state(value) or {}
                except Exception:
                    chat_state = {}
                rows.append(
                    {
                        "selector": value,
                        "title": value,
                        "stage": stage,
                        "last_message_at": chat_state.get("last_message_date_utc"),
                        "last_received_at": chat_state.get("last_sync_at") or chat_state.get("cursor_state_updated_at"),
                    }
                )
            return rows

        job = update_job(
            job_id,
            status="running",
            progress_percent=3,
            progress_label="Telegram worker взял live-sync",
            attempts_delta=1,
        )
        record_event(job_id, "Telegram live-sync запускается в celery_worker_telegram", payload={"worker": "telegram"})

        telegram_sync.state = telegram_sync.load_state()
        telegram_sync.request_source_reload()
        await telegram_sync.start(sync_in_background=True)

        last_label = ""
        while True:
            current = get_job(job_id)
            if current.status == "cancelled":
                record_event(job_id, "Telegram live-sync остановлен по cancel", level="warning")
                await telegram_sync.stop()
                return update_job(
                    job_id,
                    status="cancelled",
                    progress_percent=100,
                    progress_label="Telegram live-sync остановлен",
                    eta_seconds=0,
                    result={"ok": False, "cancelled_at": utc_now_iso()},
                )

            try:
                telegram_sync.refresh_runtime_control_from_disk()
            except Exception as exc:
                record_event(
                    job_id,
                    "Telegram live-sync не смог обновить control/source state",
                    level="warning",
                    payload={"error": str(exc)},
                )

            sync_control = telegram_sync.get_sync_control_status()
            if bool(sync_control.get("paused")):
                await telegram_sync.stop()
                label = f"Telegram live-sync на паузе: {sync_control.get('reason') or 'manual'}"
                update_job(
                    job_id,
                    status="running",
                    progress_percent=0,
                    progress_label=label,
                    eta_seconds=None,
                    chunks_done=0,
                    chunks_total=len(telegram_sync.combined_selected_chats()),
                    result={
                        "ok": True,
                        "running": False,
                        "paused": True,
                        "sync_control": sync_control,
                        "selected_sources_count": len(telegram_sync.combined_selected_chats()),
                        "enabled_sources_count": 0,
                        "active_sources_count": 0,
                        "active_sources": [],
                        "updated_at": utc_now_iso(),
                    },
                )
                if label != last_label:
                    record_event(job_id, label, payload={"paused": True})
                    last_label = label
                await asyncio.sleep(5.0)
                continue

            sync_task = getattr(telegram_sync, "_sync_task", None)
            if sync_task is None or sync_task.done():
                record_event(job_id, "Telegram live-sync перезапускается после паузы или смены источников", payload={"reason": "resume-or-source-change"})
                telegram_sync.request_source_reload()
                await telegram_sync.start(sync_in_background=True)

            selected_count = len(telegram_sync.combined_selected_chats())
            enabled_count = len(getattr(telegram_sync, "_enabled_chat_keys", set()) or set())
            setup_tasks = [
                task
                for task in (getattr(telegram_sync, "_chat_setup_tasks", {}) or {}).values()
                if task and not task.done()
            ]
            setup_task_sources = _task_sources(getattr(telegram_sync, "_chat_setup_tasks", {}) or {}, "setup")
            backfill_tasks = [
                task
                for task in (getattr(telegram_sync, "_chat_backfill_tasks", {}) or {}).values()
                if task and not task.done()
            ]
            backfill_task_sources = _task_sources(getattr(telegram_sync, "_chat_backfill_tasks", {}) or {}, "history")
            media_tasks = [
                task
                for task in (getattr(telegram_sync, "_chat_media_backfill_tasks", {}) or {}).values()
                if task and not task.done()
            ]
            media_task_sources = _task_sources(getattr(telegram_sync, "_chat_media_backfill_tasks", {}) or {}, "media")
            active_sources = [*setup_task_sources, *backfill_task_sources, *media_task_sources]
            sync_task = getattr(telegram_sync, "_sync_task", None)
            running = bool(sync_task and not sync_task.done())
            progress = 100.0 if selected_count <= 0 else min(95.0, max(10.0, (enabled_count / max(1, selected_count)) * 90.0))
            label = (
                f"Telegram live-sync: источников {enabled_count}/{selected_count}, "
                f"setup {len(setup_tasks)}, history {len(backfill_tasks)}, media {len(media_tasks)}"
            )
            if not running:
                label = "Telegram live-sync ожидает источники или подключение"
                progress = min(progress, 25.0)

            update_job(
                job_id,
                status="running",
                progress_percent=progress,
                progress_label=label,
                eta_seconds=None,
                chunks_done=enabled_count,
                chunks_total=selected_count,
                result={
                    "ok": True,
                    "running": running,
                    "selected_sources_count": selected_count,
                    "enabled_sources_count": enabled_count,
                    "active_sources_count": len(active_sources),
                    "active_sources": active_sources[:50],
                    "updated_at": utc_now_iso(),
                },
            )
            if label != last_label:
                record_event(job_id, label, payload={"running": running, "selected": selected_count, "enabled": enabled_count})
                last_label = label
            await asyncio.sleep(5.0)

    try:
        return asyncio.run(_runner())
    except Exception as exc:
        record_event(job_id, "Telegram live-sync worker завершился с ошибкой", level="error", payload={"error": str(exc)})
        return update_job(
            job_id,
            status="failed",
            progress_percent=100,
            progress_label="Telegram live-sync worker упал",
            eta_seconds=0,
            error=str(exc),
            result={"ok": False, "failed_at": utc_now_iso()},
        )
