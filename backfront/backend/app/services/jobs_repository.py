"""Repository layer for durable job state and events."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
except Exception:  # pragma: no cover - optional in local lightweight checks
    psycopg = None
    dict_row = None

from app.schemas.jobs import (
    JobCreatePayload,
    JobEventDTO,
    JobEventsPageDTO,
    JobProgressDTO,
    JobsPageDTO,
)
from app.services.jobs_runtime import default_queue_for_type, publish_progress_to_redis

POSTGRES_DSN = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("XFILES_POSTGRES_DSN")
    or os.environ.get("POSTGRES_DSN")
    or ""
).strip()
POSTGRES_CONNECT_TIMEOUT_SEC = max(1, int(os.environ.get("XFILES_POSTGRES_CONNECT_TIMEOUT", "2") or "2"))
JOB_EVENTS_RETENTION_DAYS = max(1, int(os.environ.get("XFILES_JOB_EVENTS_RETENTION_DAYS", "14") or "14"))
JOB_EVENTS_RETENTION_MAX_PER_JOB = max(100, int(os.environ.get("XFILES_JOB_EVENTS_RETENTION_MAX_PER_JOB", "500") or "500"))

_schema_ready = False
_schema_lock = threading.Lock()
_memory_jobs: Dict[str, JobProgressDTO] = {}
_memory_events: Dict[str, List[JobEventDTO]] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _pg_available() -> bool:
    return bool(POSTGRES_DSN and psycopg is not None)


def _connect():
    if not _pg_available():
        raise RuntimeError("PostgreSQL is not configured for jobs")
    kwargs: Dict[str, Any] = {"connect_timeout": POSTGRES_CONNECT_TIMEOUT_SEC}
    if dict_row is not None:
        kwargs["row_factory"] = dict_row
    return psycopg.connect(POSTGRES_DSN, **kwargs)  # type: ignore[attr-defined]


def ensure_job_schema() -> bool:
    """Create job-related tables once; return False when Postgres is unavailable."""
    global _schema_ready
    if _schema_ready:
        return True
    if not _pg_available():
        return False
    with _schema_lock:
        if _schema_ready:
            return True
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS selected_sources (
                        selector text PRIMARY KEY,
                        enabled boolean NOT NULL DEFAULT true,
                        payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        updated_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id text PRIMARY KEY,
                        type text NOT NULL,
                        queue_name text NOT NULL,
                        status text NOT NULL,
                        progress_percent double precision NOT NULL DEFAULT 0,
                        progress_label text NOT NULL DEFAULT '',
                        eta_seconds double precision,
                        payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                        result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                        error_text text,
                        attempts integer NOT NULL DEFAULT 0,
                        chunks_done integer NOT NULL DEFAULT 0,
                        chunks_total integer NOT NULL DEFAULT 0,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        started_at timestamptz,
                        finished_at timestamptz,
                        updated_at timestamptz NOT NULL DEFAULT now(),
                        last_chunk_at timestamptz
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_events (
                        id bigserial PRIMARY KEY,
                        job_id text NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                        level text NOT NULL DEFAULT 'info',
                        message text NOT NULL,
                        payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_errors (
                        id bigserial PRIMARY KEY,
                        job_id text NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                        error_text text NOT NULL,
                        payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_type ON jobs(status, type)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job_created ON job_events(job_id, created_at DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_job_events_created ON job_events(created_at DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_job_errors_job_created ON job_errors(job_id, created_at DESC)")
                _prune_job_events_locked(cur)
            conn.commit()
        _schema_ready = True
    return True


def _prune_job_events_locked(cur: Any) -> None:
    cur.execute(
        "DELETE FROM job_events WHERE created_at < now() - (%s || ' days')::interval",
        (JOB_EVENTS_RETENTION_DAYS,),
    )
    cur.execute(
        """
        DELETE FROM job_events
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (PARTITION BY job_id ORDER BY created_at DESC, id DESC) AS rn
                FROM job_events
            ) ranked
            WHERE rn > %s
        )
        """,
        (JOB_EVENTS_RETENTION_MAX_PER_JOB,),
    )


def _row_to_job(row: Dict[str, Any]) -> JobProgressDTO:
    return JobProgressDTO(
        job_id=str(row.get("id") or row.get("job_id") or ""),
        type=str(row.get("type") or "unknown"),
        queue_name=str(row.get("queue_name") or "default"),
        status=str(row.get("status") or "idle"),
        progress_percent=float(row.get("progress_percent") or 0),
        progress_label=str(row.get("progress_label") or ""),
        eta_seconds=row.get("eta_seconds"),
        attempts=int(row.get("attempts") or 0),
        chunks_done=int(row.get("chunks_done") or 0),
        chunks_total=int(row.get("chunks_total") or 0),
        last_chunk_at=_iso(row.get("last_chunk_at")),
        queue_started_at=_iso(row.get("created_at")),
        payload=_json_dict(row.get("payload_json")),
        result=_json_dict(row.get("result_json")),
        error=row.get("error_text"),
        created_at=_iso(row.get("created_at")),
        started_at=_iso(row.get("started_at")),
        finished_at=_iso(row.get("finished_at")),
        updated_at=_iso(row.get("updated_at")),
    )


def _memory_upsert(job: JobProgressDTO) -> JobProgressDTO:
    _memory_jobs[job.job_id] = job
    publish_progress_to_redis(job)
    return job


def record_event(job_id: str, message: str, *, level: str = "info", payload: Optional[Dict[str, Any]] = None) -> JobEventDTO:
    payload = payload or {}
    if ensure_job_schema():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_events (job_id, level, message, payload_json)
                    VALUES (%s, %s, %s, %s::jsonb)
                    RETURNING id, job_id, level, message, payload_json, created_at
                    """,
                    (job_id, level, message, json.dumps(payload, ensure_ascii=False)),
                )
                row = cur.fetchone()
            conn.commit()
        return JobEventDTO(
            id=int(row["id"]),
            job_id=str(row["job_id"]),
            level=str(row["level"]),
            message=str(row["message"]),
            payload=_json_dict(row.get("payload_json")),
            created_at=_iso(row.get("created_at")),
        )
    item = JobEventDTO(job_id=job_id, level=level, message=message, payload=payload, created_at=_utc_now().isoformat())
    _memory_events.setdefault(job_id, []).append(item)
    return item


def create_job(payload: JobCreatePayload) -> JobProgressDTO:
    job_id = uuid.uuid4().hex
    job_type = str(payload.type or "llm_analysis").strip() or "llm_analysis"
    queue_name = str(payload.queue_name or default_queue_for_type(job_type)).strip() or "llm.analysis"
    if ensure_job_schema():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (id, type, queue_name, status, progress_percent, progress_label, payload_json)
                    VALUES (%s, %s, %s, 'queued', 0, %s, %s::jsonb)
                    RETURNING *
                    """,
                    (
                        job_id,
                        job_type,
                        queue_name,
                        "Задача поставлена в очередь",
                        json.dumps(payload.payload, ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        job = _row_to_job(row)
    else:
        job = JobProgressDTO(
            job_id=job_id,
            type=job_type,
            queue_name=queue_name,
            status="queued",
            progress_label="Задача поставлена в очередь",
            payload=payload.payload,
            created_at=_utc_now().isoformat(),
            updated_at=_utc_now().isoformat(),
        )
        _memory_upsert(job)
    record_event(job_id, "Задача создана", payload={"type": job_type, "queue_name": queue_name})
    publish_progress_to_redis(job)
    return job

def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress_percent: Optional[float] = None,
    progress_label: Optional[str] = None,
    eta_seconds: Optional[float] = None,
    chunks_done: Optional[int] = None,
    chunks_total: Optional[int] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    attempts_delta: int = 0,
) -> JobProgressDTO:
    current = get_job(job_id)
    next_status = status or current.status
    now = _utc_now()
    started_at = current.started_at
    finished_at = current.finished_at
    if next_status == "running" and not started_at:
        started_at = now.isoformat()
    if next_status in {"done", "failed", "error", "cancelled"}:
        finished_at = now.isoformat()

    if ensure_job_schema():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = %s,
                        progress_percent = %s,
                        progress_label = %s,
                        eta_seconds = %s,
                        chunks_done = %s,
                        chunks_total = %s,
                        result_json = %s::jsonb,
                        error_text = %s,
                        attempts = attempts + %s,
                        started_at = COALESCE(started_at, %s),
                        finished_at = %s,
                        updated_at = now(),
                        last_chunk_at = CASE WHEN %s::integer > chunks_done THEN now() ELSE last_chunk_at END
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        next_status,
                        progress_percent if progress_percent is not None else current.progress_percent,
                        progress_label if progress_label is not None else current.progress_label,
                        eta_seconds if eta_seconds is not None else current.eta_seconds,
                        chunks_done if chunks_done is not None else current.chunks_done,
                        chunks_total if chunks_total is not None else current.chunks_total,
                        json.dumps(result if result is not None else current.result, ensure_ascii=False),
                        error if error is not None else current.error,
                        attempts_delta,
                        started_at,
                        finished_at,
                        chunks_done if chunks_done is not None else current.chunks_done,
                        job_id,
                    ),
                )
                row = cur.fetchone()
                if error:
                    cur.execute(
                        "INSERT INTO job_errors (job_id, error_text, payload_json) VALUES (%s, %s, %s::jsonb)",
                        (job_id, error, json.dumps({"status": next_status}, ensure_ascii=False)),
                    )
            conn.commit()
        job = _row_to_job(row)
    else:
        job = current.model_copy(
            update={
                "status": next_status,
                "progress_percent": progress_percent if progress_percent is not None else current.progress_percent,
                "progress_label": progress_label if progress_label is not None else current.progress_label,
                "eta_seconds": eta_seconds if eta_seconds is not None else current.eta_seconds,
                "chunks_done": chunks_done if chunks_done is not None else current.chunks_done,
                "chunks_total": chunks_total if chunks_total is not None else current.chunks_total,
                "result": result if result is not None else current.result,
                "error": error if error is not None else current.error,
                "attempts": current.attempts + attempts_delta,
                "started_at": started_at,
                "finished_at": finished_at,
                "updated_at": now.isoformat(),
            }
        )
        _memory_upsert(job)
    publish_progress_to_redis(job)
    if progress_label:
        record_event(job_id, progress_label, payload={"status": next_status, "progress_percent": job.progress_percent})
    return job


def get_job(job_id: str) -> JobProgressDTO:
    if ensure_job_schema():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
        if row:
            job = _row_to_job(row)
            publish_progress_to_redis(job)
            return job
    return _memory_jobs.get(
        job_id,
        JobProgressDTO(
            job_id=job_id,
            status="idle",
            progress_percent=0,
            progress_label="очередь пуста",
        ),
    )


def _page(items: Iterable[Any], page: int, page_size: int) -> Tuple[List[Any], int, int]:
    all_items = list(items)
    total = len(all_items)
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return all_items[start:end], total, max(1, (total + page_size - 1) // page_size)


def list_jobs(page: int = 1, page_size: int = 20, status: Optional[str] = None, job_type: Optional[str] = None) -> JobsPageDTO:
    if ensure_job_schema():
        filters: List[str] = []
        params: List[Any] = []
        if status:
            filters.append("status = %s")
            params.append(status)
        if job_type:
            filters.append("type = %s")
            params.append(job_type)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        offset = max(0, (page - 1) * page_size)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) AS total FROM jobs {where}", params)
                total = int(cur.fetchone()["total"])
                cur.execute(
                    f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    [*params, page_size, offset],
                )
                rows = cur.fetchall()
        items = [_row_to_job(row) for row in rows]
        return JobsPageDTO(items=items, total=total, page=page, page_size=page_size, total_pages=max(1, (total + page_size - 1) // page_size))
    items = list(_memory_jobs.values())
    if status:
        items = [item for item in items if item.status == status]
    if job_type:
        items = [item for item in items if item.type == job_type]
    items.sort(key=lambda item: item.created_at or "", reverse=True)
    page_items, total, total_pages = _page(items, page, page_size)
    return JobsPageDTO(items=page_items, total=total, page=page, page_size=page_size, total_pages=total_pages)


def list_events(job_id: str, page: int = 1, page_size: int = 50) -> JobEventsPageDTO:
    if ensure_job_schema():
        offset = max(0, (page - 1) * page_size)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS total FROM job_events WHERE job_id = %s", (job_id,))
                total = int(cur.fetchone()["total"])
                cur.execute(
                    """
                    SELECT id, job_id, level, message, payload_json, created_at
                    FROM job_events
                    WHERE job_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (job_id, page_size, offset),
                )
                rows = cur.fetchall()
        items = [
            JobEventDTO(
                id=int(row["id"]),
                job_id=str(row["job_id"]),
                level=str(row["level"]),
                message=str(row["message"]),
                payload=_json_dict(row.get("payload_json")),
                created_at=_iso(row.get("created_at")),
            )
            for row in rows
        ]
        return JobEventsPageDTO(items=items, total=total, page=page, page_size=page_size, total_pages=max(1, (total + page_size - 1) // page_size))
    events = list(reversed(_memory_events.get(job_id, [])))
    page_items, total, total_pages = _page(events, page, page_size)
    return JobEventsPageDTO(items=page_items, total=total, page=page, page_size=page_size, total_pages=total_pages)
