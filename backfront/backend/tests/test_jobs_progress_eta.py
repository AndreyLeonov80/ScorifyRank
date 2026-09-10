from __future__ import annotations

import unittest
from unittest.mock import patch

from app.schemas.jobs import JobCreatePayload
from app.services import jobs


class JobsProgressEtaTest(unittest.TestCase):
    def setUp(self) -> None:
        jobs._memory_jobs.clear()
        jobs._memory_events.clear()

    def test_long_running_job_types_report_progress_eta_and_terminal_status(self) -> None:
        cases = [
            ("telegram_import", "telegram.import"),
            ("data_source_sync", "data_source.sync"),
            ("data_source_delete_cache", "data_source.delete_cache"),
            ("data_source_full_rescan", "data_source.full_rescan"),
        ]

        with patch.object(jobs, "ensure_job_schema", return_value=False):
            for job_type, expected_queue in cases:
                with self.subTest(job_type=job_type):
                    created = jobs.create_job(
                        JobCreatePayload(
                            type=job_type,
                            payload={"simulation_steps": 3, "simulation_step_sec": 0},
                        )
                    )
                    self.assertEqual(expected_queue, created.queue_name)
                    self.assertEqual("queued", created.status)
                    self.assertEqual(0, created.progress_percent)

                    finished = jobs.run_job(created.job_id)

                    self.assertEqual("done", finished.status)
                    self.assertEqual(100, finished.progress_percent)
                    self.assertEqual(0, finished.eta_seconds)
                    self.assertEqual(3, finished.chunks_done)
                    self.assertEqual(3, finished.chunks_total)
                    self.assertTrue(finished.finished_at)
                    self.assertTrue(finished.result.get("ok"))

                    events = jobs.list_events(created.job_id)
                    self.assertGreaterEqual(events.total, 1)


if __name__ == "__main__":
    unittest.main()

