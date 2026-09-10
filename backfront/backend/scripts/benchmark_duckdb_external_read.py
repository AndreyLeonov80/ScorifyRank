#!/usr/bin/env python3
"""Benchmark backend endpoints while an external service reads DuckDB snapshot.

The script intentionally opens gramlead-read.duckdb, never gramlead.duckdb.
It measures three hot UI paths during snapshot reads:
- /api/payme/source-stats
- /api/payme/leads/{lead}/messages
- /api/payme/search/messages
"""

from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote

import requests


DEFAULT_SNAPSHOT = "/data/db/duckdb/gramlead-read.duckdb"


def _timed_get(base_url: str, path: str, timeout: float) -> float:
    started = time.perf_counter()
    response = requests.get(f"{base_url.rstrip('/')}{path}", timeout=timeout)
    response.raise_for_status()
    return time.perf_counter() - started


def _snapshot_heavy_read(snapshot_path: Path) -> Dict[str, int]:
    import duckdb  # type: ignore

    conn = duckdb.connect(str(snapshot_path), read_only=True)
    try:
        row = conn.execute(
            """
            SELECT
                count(*) AS rows_total,
                count(DISTINCT source_jsonl) AS sources_total
            FROM messages_raw
            """
        ).fetchone()
        return {"rows_total": int(row[0] or 0), "sources_total": int(row[1] or 0)}
    finally:
        conn.close()


def run_benchmark(base_url: str, snapshot_path: Path, lead: str, rounds: int, timeout: float) -> Dict[str, object]:
    if snapshot_path.name != "gramlead-read.duckdb":
        raise ValueError("Benchmark must read gramlead-read.duckdb snapshot, not writer DuckDB")
    if not snapshot_path.exists():
        raise FileNotFoundError(f"DuckDB snapshot not found: {snapshot_path}")

    endpoint_paths = {
        "source_stats": "/api/payme/source-stats?page=1&page_size=5",
        "chat_latest": f"/api/payme/leads/{quote(lead)}/messages?offset=0&limit=30",
        "search": "/api/payme/search/messages?page=1&page_size=5&query=%D0%B0",
    }
    timings: Dict[str, List[float]] = {name: [] for name in endpoint_paths}
    snapshot_counts: List[Dict[str, int]] = []
    for _ in range(max(1, int(rounds))):
        snapshot_counts.append(_snapshot_heavy_read(snapshot_path))
        for name, path in endpoint_paths.items():
            timings[name].append(_timed_get(base_url, path, timeout))

    return {
        "snapshot_path": str(snapshot_path),
        "snapshot_counts_last": snapshot_counts[-1] if snapshot_counts else {},
        "timings_sec": {
            name: {
                "avg": round(statistics.mean(values), 4),
                "max": round(max(values), 4),
                "samples": len(values),
            }
            for name, values in timings.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8009")
    parser.add_argument("--snapshot", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--lead", default="breakfast_with_harskii")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    result = run_benchmark(args.base_url, Path(args.snapshot), args.lead, args.rounds, args.timeout)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
