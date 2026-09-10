"""Simple PostgreSQL polling worker kept as a no-RabbitMQ fallback."""

from __future__ import annotations

import os
import time

from app.services import jobs as jobs_service


def run_once() -> int:
    page = jobs_service.list_jobs(page=1, page_size=1, status="queued")
    if not page.items:
        return 0
    jobs_service.run_job(page.items[0].job_id)
    return 1


def main() -> None:
    interval = max(1.0, float(os.environ.get("POSTGRES_WORKER_POLL_INTERVAL_SEC", "2") or "2"))
    while True:
        processed = run_once()
        if not processed:
            time.sleep(interval)


if __name__ == "__main__":
    main()
