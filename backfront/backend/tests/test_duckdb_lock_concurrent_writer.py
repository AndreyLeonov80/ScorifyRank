from __future__ import annotations

from pathlib import Path
import tempfile

import duckdb

from app.core.error_taxonomy import classify_error_text, recovery_hint


def test_duckdb_concurrent_writer_conflict_is_classified_as_lock_risk() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "concurrent.duckdb"
        backend_conn = duckdb.connect(str(db_path))
        worker_conn = duckdb.connect(str(db_path))
        try:
            backend_conn.execute("CREATE TABLE messages_raw(row_hash VARCHAR PRIMARY KEY, value INTEGER)")
            backend_conn.execute("INSERT INTO messages_raw VALUES ('same-row', 1)")

            backend_conn.begin()
            backend_conn.execute("UPDATE messages_raw SET value = 2 WHERE row_hash = 'same-row'")
            try:
                worker_conn.execute("UPDATE messages_raw SET value = 3 WHERE row_hash = 'same-row'")
            except Exception as exc:
                error = exc
            else:  # pragma: no cover - DuckDB should raise on same-row concurrent update.
                error = RuntimeError("DuckDB concurrent writer conflict did not happen")
        finally:
            backend_conn.rollback()
            backend_conn.close()
            worker_conn.close()

    assert classify_error_text(error) == "duckdb_locked"
    assert "DuckDB" in recovery_hint("duckdb_locked")
