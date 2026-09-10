"""RabbitMQ/Celery enqueue adapter for durable jobs."""

from __future__ import annotations

from typing import Callable

from app.schemas.jobs import JobCreateDTO, JobProgressDTO


def enqueue_created_job(
    job: JobProgressDTO,
    *,
    get_job: Callable[[str], JobProgressDTO],
    record_event: Callable[..., object],
) -> JobCreateDTO:
    queued_via = "postgres"
    try:
        from app.celery_app import celery_app

        task_name = (
            "app.workers.celery_tasks.run_telegram_sync_live"
            if str(job.type or "") == "telegram_sync"
            else "app.workers.celery_tasks.run_job"
        )
        celery_app.send_task(task_name, args=[job.job_id], queue=job.queue_name)
        queued_via = "rabbitmq"
        record_event(job.job_id, "Задача отправлена в RabbitMQ", payload={"queue": job.queue_name, "task": task_name})
    except Exception as exc:
        record_event(
            job.job_id,
            "RabbitMQ/Celery недоступны, задача остается в PostgreSQL",
            level="warning",
            payload={"error": str(exc)},
        )
    return JobCreateDTO(
        job_id=job.job_id,
        status=job.status,
        queue_name=job.queue_name,
        message=f"Задача поставлена в очередь ({queued_via})",
        job=get_job(job.job_id),
    )
