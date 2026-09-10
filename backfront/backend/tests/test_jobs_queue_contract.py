from __future__ import annotations

import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.schemas.jobs import JobCreateDTO
from app.schemas.jobs import JobCreatePayload
from app.services import jobs
from app.services import jobs_runtime


class FakeRedisPipeline:
    def __init__(self, store):
        self.store = store
        self.ops = []

    def set(self, key, value, ex=None):
        self.ops.append((key, value, ex))
        return self

    def execute(self):
        for key, value, _ex in self.ops:
            self.store[key] = value


class FakeRedis:
    def __init__(self):
        self.store = {}

    def pipeline(self):
        return FakeRedisPipeline(self.store)


class JobsQueueContractTest(unittest.TestCase):
    def setUp(self) -> None:
        jobs._memory_jobs.clear()
        jobs._memory_events.clear()
        jobs_runtime._redis_client = None

    def test_memory_fallback_creates_and_runs_job_with_progress(self) -> None:
        with patch.object(jobs, "ensure_job_schema", return_value=False):
            created = jobs.enqueue_job(
                JobCreatePayload(
                    type="llm_analysis",
                    payload={"simulation_steps": 2, "simulation_step_sec": 0},
                )
            )
            self.assertTrue(created.ok)
            self.assertEqual("llm.analysis", created.queue_name)

            finished = jobs.run_job(created.job_id)
            self.assertEqual("done", finished.status)
            self.assertEqual(100, finished.progress_percent)
            self.assertTrue(finished.result.get("ok"))

            events = jobs.list_events(created.job_id)
            self.assertGreaterEqual(events.total, 2)

    def test_cancel_job_records_terminal_status(self) -> None:
        with patch.object(jobs, "ensure_job_schema", return_value=False):
            created = jobs.create_job(JobCreatePayload(type="reply_suggest"))
            cancelled = jobs.cancel_job(created.job_id)
            self.assertEqual("cancelled", cancelled.status)
            self.assertEqual("cancelled", jobs.get_job(created.job_id).status)

    def test_redis_progress_key_contract(self) -> None:
        fake_redis = FakeRedis()
        jobs_runtime._redis_client = fake_redis
        with patch.object(jobs, "ensure_job_schema", return_value=False):
            created = jobs.create_job(JobCreatePayload(type="llm_analysis"))
            jobs.run_job(created.job_id)

        self.assertIn(fake_redis.store[f"job:{created.job_id}:progress"], {"100", "100.0"})
        self.assertEqual("done", fake_redis.store[f"job:{created.job_id}:status"])
        self.assertEqual("Задача завершена", fake_redis.store[f"job:{created.job_id}:last_event"])
        self.assertEqual("0", fake_redis.store[f"job:{created.job_id}:eta"])
        self.assertEqual("0", fake_redis.store["counter:queue:llm.analysis:running"])

    def test_rabbitmq_enqueue_failure_is_visible_and_not_silent(self) -> None:
        with patch.object(jobs, "ensure_job_schema", return_value=False):
            fake_celery_module = SimpleNamespace(
                celery_app=SimpleNamespace(send_task=Mock(side_effect=RuntimeError("broker down"))),
            )
            with patch.dict("sys.modules", {"app.celery_app": fake_celery_module}):
                created = jobs.enqueue_job(JobCreatePayload(type="telegram_import"))

        self.assertEqual("telegram.import", created.queue_name)
        self.assertIn("postgres", created.message)
        events = jobs.list_events(created.job_id)
        warnings = [item for item in events.items if item.level == "warning"]
        self.assertTrue(warnings)
        self.assertIn("RabbitMQ/Celery недоступны", warnings[-1].message)
        self.assertEqual("broker down", warnings[-1].payload["error"])

    def test_error_update_records_retry_and_dead_letter_state(self) -> None:
        fake_redis = FakeRedis()
        jobs_runtime._redis_client = fake_redis
        with patch.object(jobs, "ensure_job_schema", return_value=False):
            created = jobs.create_job(JobCreatePayload(type="llm_analysis"))
            failed = jobs.update_job(
                created.job_id,
                status="error",
                progress_percent=100,
                progress_label="Worker failed",
                error="boom",
                attempts_delta=1,
            )

        self.assertEqual("error", failed.status)
        self.assertEqual("boom", failed.error)
        self.assertEqual(1, failed.attempts)
        self.assertTrue(failed.finished_at)
        self.assertEqual("error", fake_redis.store[f"job:{created.job_id}:status"])
        self.assertEqual("Worker failed", fake_redis.store[f"job:{created.job_id}:last_event"])
        events = jobs.list_events(created.job_id)
        self.assertTrue(any(item.message == "Worker failed" for item in events.items))

    def test_stale_telegram_sync_job_is_replaced(self) -> None:
        with patch.object(jobs, "ensure_job_schema", return_value=False):
            stale = jobs.create_job(JobCreatePayload(type="telegram_sync"))
            stale = jobs.update_job(stale.job_id, status="running", progress_percent=40, progress_label="old worker")
            jobs._memory_jobs[stale.job_id] = stale.model_copy(
                update={
                    "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                    "last_chunk_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                }
            )

            def fake_enqueue(job, *, get_job, record_event):
                return JobCreateDTO(
                    job_id=job.job_id,
                    status=job.status,
                    queue_name=job.queue_name,
                    message="fake queued",
                    job=get_job(job.job_id),
                )

            with patch.object(jobs, "enqueue_created_job", side_effect=fake_enqueue):
                created = jobs.ensure_telegram_sync_job(reason="test-stale-restart")

            self.assertNotEqual(stale.job_id, created.job_id)
            self.assertEqual("failed", jobs.get_job(stale.job_id).status)
            self.assertEqual("queued", jobs.get_job(created.job_id).status)
            self.assertEqual("telegram_sync_stale_heartbeat", jobs.get_job(stale.job_id).error)

    def test_heavy_operations_have_dedicated_job_queues(self) -> None:
        expected = {
            "telegram_import": "telegram.import",
            "telegram_sync": "telegram.sync",
            "jsonl_ingest": "jsonl.ingest",
            "duckdb_preprocess": "duckdb.preprocess",
            "llm_analysis": "llm.analysis",
            "ocr_media": "ocr.media",
            "cache_warm": "cache.warm",
            "data_source_sync": "data_source.sync",
            "data_source_full_rescan": "data_source.full_rescan",
            "data_source_preprocess": "data_source.preprocess",
        }
        for job_type, queue_name in expected.items():
            with self.subTest(job_type=job_type):
                self.assertEqual(queue_name, jobs_runtime.default_queue_for_type(job_type))

    def test_worker_queues_declared_in_compose_exist_in_celery_app(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
        celery_source = (repo_root / "backfront/backend/app/celery_app.py").read_text(encoding="utf-8")
        declared = set(re.findall(r'"([a-z_]+\.[a-z_]+)"', celery_source))
        worker_queues = set()
        for queue_arg in re.findall(r'"-Q",\s*"([^"]+)"', compose):
            worker_queues.update(queue.strip() for queue in queue_arg.split(",") if queue.strip())

        self.assertTrue(worker_queues)
        self.assertLessEqual(worker_queues, declared)


if __name__ == "__main__":
    unittest.main()
