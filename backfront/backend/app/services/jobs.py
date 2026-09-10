"""Durable jobs facade plus optional RabbitMQ/Celery enqueue and runner bridge."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from app.schemas.jobs import JobCancelDTO, JobCreateDTO, JobCreatePayload, JobProgressDTO
from app.services.jobs_queue import enqueue_created_job
from app.services.jobs_repository import (
    _memory_events,
    _memory_jobs,
    create_job,
    ensure_job_schema,
    get_job,
    list_events,
    list_jobs,
    record_event,
    update_job,
)
from app.services.jobs_runner import run_simulated_job
from app.services.jobs_runner import run_telegram_sync_job


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


TELEGRAM_SYNC_STALE_AFTER_SEC = max(
    30,
    int(os.environ.get("XFILES_TELEGRAM_SYNC_STALE_AFTER_SEC", "30") or "30"),
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def is_stale_telegram_sync_job(job: JobProgressDTO | None, *, now: datetime | None = None) -> bool:
    if job is None:
        return False
    if str(job.type or "") != "telegram_sync":
        return False
    if str(job.status or "") not in {"running", "queued", "pending"}:
        return False
    heartbeat = _parse_dt(job.updated_at) or _parse_dt(job.last_chunk_at) or _parse_dt(job.started_at) or _parse_dt(job.created_at)
    if heartbeat is None:
        return True
    return ((now or _utc_now()) - heartbeat).total_seconds() > TELEGRAM_SYNC_STALE_AFTER_SEC


def enqueue_job(payload: JobCreatePayload) -> JobCreateDTO:
    job = create_job(payload)
    return enqueue_created_job(job, get_job=get_job, record_event=record_event)


def latest_job_by_type(job_type: str) -> JobProgressDTO | None:
    page = list_jobs(page=1, page_size=1, job_type=job_type)
    return page.items[0] if page.items else None


def latest_active_job_by_type(job_type: str) -> JobProgressDTO | None:
    for status in ("running", "queued", "pending"):
        page = list_jobs(page=1, page_size=1, status=status, job_type=job_type)
        if page.items:
            return page.items[0]
    return None


def ensure_telegram_sync_job(reason: str = "manual") -> JobCreateDTO:
    active = latest_active_job_by_type("telegram_sync")
    if is_stale_telegram_sync_job(active):
        assert active is not None
        message = "Telegram live-sync heartbeat устарел, задача будет перезапущена"
        update_job(
            active.job_id,
            status="failed",
            progress_percent=min(100, max(0, active.progress_percent)),
            progress_label=message,
            eta_seconds=0,
            error="telegram_sync_stale_heartbeat",
            result={"ok": False, "reason": reason, "stale_job": active.job_id},
        )
        record_event(active.job_id, message, level="warning", payload={"reason": reason})
        active = None
    if active is not None:
        record_event(
            active.job_id,
            "Telegram live-sync уже запущен",
            payload={"reason": reason, "status": active.status},
        )
        return JobCreateDTO(
            job_id=active.job_id,
            status=active.status,
            queue_name=active.queue_name,
            message="Telegram live-sync уже работает",
            job=get_job(active.job_id),
        )
    return enqueue_job(
        JobCreatePayload(
            type="telegram_sync",
            payload={"reason": reason, "created_at": _utc_now().isoformat()},
        )
    )


def cancel_job(job_id: str) -> JobCancelDTO:
    job = update_job(job_id, status="cancelled", progress_percent=100, progress_label="Задача отменена", eta_seconds=0)
    record_event(job_id, "Задача отменена пользователем", level="warning")
    return JobCancelDTO(job_id=job.job_id, status=job.status)


def run_job(job_id: str) -> JobProgressDTO:
    """Worker entry point used by Celery tasks and local smoke checks."""
    job = get_job(job_id)
    if job.type == "telegram_sync":
        return run_telegram_sync_job(
            job_id,
            get_job=get_job,
            update_job=update_job,
            record_event=record_event,
            utc_now_iso=lambda: _utc_now().isoformat(),
        )
    return run_simulated_job(
        job_id,
        get_job=get_job,
        update_job=update_job,
        record_event=record_event,
        utc_now_iso=lambda: _utc_now().isoformat(),
    )
