from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

from app import legacy_runtime as runtime


def test_lock_status_warns_when_read_snapshot_is_stale(tmp_path: Path) -> None:
    writer_path = tmp_path / "gramlead.duckdb"
    read_path = tmp_path / "gramlead-read.duckdb"
    writer_path.write_bytes(b"writer")
    read_path.write_bytes(b"snapshot")
    old_ts = time.time() - 3600
    os.utime(read_path, (old_ts, old_ts))

    with patch.object(runtime, "DUCKDB_PATH", writer_path), patch.object(runtime, "DUCKDB_READ_PATH", read_path):
        with patch.object(runtime, "_DUCKDB_READ_SNAPSHOT_STALE_WARN_SEC", 60, create=True):
            status = runtime._duckdb_lock_status_snapshot()

    assert status["read_snapshot_exists"] is True
    assert status["read_snapshot_stale"] is True
    assert "snapshot" in status["warning"].lower()


def test_duckdb_external_benchmark_script_documents_required_targets() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_duckdb_external_read.py"
    text = script.read_text(encoding="utf-8")

    assert "/api/payme/source-stats" in text
    assert "/api/payme/leads/" in text
    assert "/api/payme/search/messages" in text
    assert "gramlead-read.duckdb" in text
