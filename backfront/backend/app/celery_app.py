"""Celery application for gramLead background jobs."""

from __future__ import annotations

import os

from celery import Celery
from kombu import Exchange, Queue


BROKER_URL = os.environ.get("CELERY_BROKER_URL") or os.environ.get("RABBITMQ_URL") or "memory://"
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND") or os.environ.get("REDIS_URL") or "rpc://"


def _celery_time_limit_from_env(name: str, default: str) -> int | None:
    raw = str(os.environ.get(name, default) or default).strip().lower()
    if raw in {"0", "none", "null", "false", "off", "unlimited"}:
        return None
    return int(raw)

celery_app = Celery(
    "gramlead_jobs",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.workers.celery_tasks"],
)

DEFAULT_EXCHANGE = Exchange("gramlead", type="direct", durable=True)
DEAD_LETTER_EXCHANGE = Exchange("gramlead.dlx", type="direct", durable=True)
QUEUE_NAMES = [
    "telegram.import",
    "telegram.sync",
    "jsonl.ingest",
    "duckdb.preprocess",
    "llm.analysis",
    "lead.scoring",
    "reply.suggest",
    "digest.generate",
    "cache.warm",
    "ocr.media",
    "export.crm",
]

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=int(os.environ.get("CELERY_WORKER_PREFETCH_MULTIPLIER", "1") or "1"),
    task_reject_on_worker_lost=True,
    task_default_delivery_mode="persistent",
    task_default_queue="llm.analysis",
    task_default_exchange=DEFAULT_EXCHANGE.name,
    task_default_exchange_type=DEFAULT_EXCHANGE.type,
    task_default_routing_key="llm.analysis",
    task_queues=[
        *[
            Queue(
                name,
                exchange=DEFAULT_EXCHANGE,
                routing_key=name,
                durable=True,
                queue_arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name},
            )
            for name in QUEUE_NAMES
        ],
        Queue("dead_letter", exchange=DEAD_LETTER_EXCHANGE, routing_key="#", durable=True),
    ],
    task_routes={
        "app.workers.celery_tasks.run_telegram_sync_live": {"queue": "telegram.sync"},
        "app.workers.celery_tasks.sync_telegram_channel": {"queue": "telegram.sync"},
        "app.workers.celery_tasks.ingest_jsonl_file": {"queue": "jsonl.ingest"},
        "app.workers.celery_tasks.preprocess_duckdb_batch": {"queue": "duckdb.preprocess"},
        "app.workers.celery_tasks.analyze_batch": {"queue": "llm.analysis"},
        "app.workers.celery_tasks.score_lead": {"queue": "lead.scoring"},
        "app.workers.celery_tasks.generate_reply_suggestion": {"queue": "reply.suggest"},
        "app.workers.celery_tasks.build_daily_digest": {"queue": "digest.generate"},
        "app.workers.celery_tasks.warm_sender_stats_cache": {"queue": "cache.warm"},
        "app.workers.celery_tasks.export_to_crm": {"queue": "export.crm"},
    },
    task_time_limit=_celery_time_limit_from_env("CELERY_TASK_TIME_LIMIT", "900"),
    task_soft_time_limit=_celery_time_limit_from_env("CELERY_TASK_SOFT_TIME_LIMIT", "840"),
    result_expires=int(os.environ.get("CELERY_RESULT_EXPIRES", "86400") or "86400"),
)
