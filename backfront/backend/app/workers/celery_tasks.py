"""Celery tasks that execute durable jobs and update progress."""

from __future__ import annotations

from typing import Any, Dict

from app.celery_app import celery_app
from app.services import jobs as jobs_service


@celery_app.task(
    name="app.workers.celery_tasks.run_job",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_job(self, job_id: str) -> Dict[str, Any]:
    job = jobs_service.run_job(job_id)
    return {"job_id": job.job_id, "status": job.status, "progress_percent": job.progress_percent}


@celery_app.task(
    name="app.workers.celery_tasks.run_telegram_sync_live",
    bind=True,
    soft_time_limit=None,
    time_limit=None,
    acks_late=False,
    reject_on_worker_lost=False,
)
def run_telegram_sync_live(self, job_id: str) -> Dict[str, Any]:
    job = jobs_service.run_job(job_id)
    return {"job_id": job.job_id, "status": job.status, "progress_percent": job.progress_percent}


@celery_app.task(name="app.workers.celery_tasks.sync_telegram_channel")
def sync_telegram_channel(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.ingest_jsonl_file")
def ingest_jsonl_file(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.preprocess_duckdb_batch")
def preprocess_duckdb_batch(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.analyze_message")
def analyze_message(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.analyze_batch")
def analyze_batch(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.extract_pain_signal")
def extract_pain_signal(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.extract_prepay_signal")
def extract_prepay_signal(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.extract_pay_signal")
def extract_pay_signal(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.score_lead")
def score_lead(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.generate_reply_suggestion")
def generate_reply_suggestion(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.build_daily_digest")
def build_daily_digest(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.warm_sender_stats_cache")
def warm_sender_stats_cache(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)


@celery_app.task(name="app.workers.celery_tasks.export_to_crm")
def export_to_crm(job_id: str) -> Dict[str, Any]:
    return run_job(job_id)
