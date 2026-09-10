"""Queue mapping and Redis progress bridge for background jobs."""

from __future__ import annotations

import os
from typing import Any

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional in local lightweight checks
    redis = None

from app.schemas.jobs import JobProgressDTO

REDIS_URL = (os.environ.get("REDIS_URL") or os.environ.get("CELERY_RESULT_BACKEND") or "").strip()

JOB_QUEUE_BY_TYPE = {
    "telegram_import": "telegram.import",
    "telegram_sync": "telegram.sync",
    "jsonl_ingest": "jsonl.ingest",
    "duckdb_preprocess": "duckdb.preprocess",
    "llm_analysis": "llm.analysis",
    "lead_scoring": "lead.scoring",
    "reply_suggest": "reply.suggest",
    "digest_generate": "digest.generate",
    "cache_warm": "cache.warm",
    "ocr_media": "ocr.media",
    "export_crm": "export.crm",
    "data_source_connect": "data_source.connect",
    "data_source_introspect": "data_source.introspect",
    "data_source_preview": "data_source.preview",
    "data_source_sync": "data_source.sync",
    "data_source_full_rescan": "data_source.full_rescan",
    "data_source_preprocess": "data_source.preprocess",
    "data_source_delete_cache": "data_source.delete_cache",
}

_redis_client: Any = None


def default_queue_for_type(job_type: str) -> str:
    return JOB_QUEUE_BY_TYPE.get(str(job_type or "").strip() or "llm_analysis", "llm.analysis")


def _redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL or redis is None:
        return None
    try:
        _redis_client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        _redis_client.ping()
    except Exception:
        _redis_client = None
    return _redis_client


def publish_progress_to_redis(job: JobProgressDTO) -> None:
    client = _redis()
    if client is None:
        return
    ttl = 60 * 60 * 24
    mapping = {
        f"job:{job.job_id}:progress": str(job.progress_percent),
        f"job:{job.job_id}:eta": "" if job.eta_seconds is None else str(job.eta_seconds),
        f"job:{job.job_id}:status": str(job.status),
        f"job:{job.job_id}:last_event": job.progress_label or "",
        f"counter:queue:{job.queue_name}:running": "1" if job.status == "running" else "0",
    }
    try:
        pipe = client.pipeline()
        for key, value in mapping.items():
            pipe.set(key, value, ex=ttl)
        pipe.execute()
    except Exception:
        return
