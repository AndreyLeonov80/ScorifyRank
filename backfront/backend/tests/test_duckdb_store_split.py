import tempfile
import unittest
from pathlib import Path

from app.storage.duckdb.connection import ensure_duckdb_available
from app.storage.duckdb.ingest import bootstrap_required, source_file_stats
from app.storage.duckdb.maintenance import HEAVY_DUCKDB_INDEXES, LIGHT_DUCKDB_INDEXES, indexes_ready_after_bootstrap
from app.storage.duckdb.queries import golden_counts_summary, golden_last_messages, lead_name_from_source_jsonl
from app.storage.duckdb.schema import DUCKDB_EXPORT_TABLES, init_schema

try:
    import duckdb
except Exception:  # pragma: no cover - optional local dependency
    duckdb = None


class DuckDBStoreSplitTest(unittest.TestCase):
    def test_schema_exports_core_tables(self) -> None:
        self.assertEqual(DUCKDB_EXPORT_TABLES["messages_raw"], "messages_raw.parquet")
        self.assertIn("file_registry", DUCKDB_EXPORT_TABLES)
        self.assertIn("crm_contacts", DUCKDB_EXPORT_TABLES)
        self.assertIn("event_messages", DUCKDB_EXPORT_TABLES)

    def test_golden_counts_source_files_and_last_messages(self) -> None:
        counts = golden_counts_summary(
            {
                "tracked_files": "2",
                "file_registry_rows": 2,
                "message_rows": 30,
                "source_files_indexed": 2,
                "duplicate_message_rows": 99,
            }
        )
        self.assertEqual(counts, {"tracked_files": 2, "file_registry_rows": 2, "message_rows": 30, "source_files_indexed": 2})

        self.assertEqual(lead_name_from_source_jsonl("nested/chat_a.jsonl"), "chat_a")
        self.assertEqual(
            golden_last_messages(
                [
                    {"source_jsonl": "b.jsonl", "message_id": "2", "text": "B", "date_utc_raw": "2026"},
                    {"source_jsonl": "a.jsonl", "message_id": 1, "text": "A", "date_utc_raw": "2025"},
                ]
            ),
            [
                {"source_jsonl": "a.jsonl", "message_id": 1, "text": "A", "date_utc_raw": "2025"},
                {"source_jsonl": "b.jsonl", "message_id": 2, "text": "B", "date_utc_raw": "2026"},
            ],
        )

    def test_ingest_and_maintenance_helpers(self) -> None:
        self.assertTrue(bootstrap_required({"tracked_files": 0, "message_rows": 0}, force_full=False))
        self.assertFalse(bootstrap_required({"tracked_files": 1, "message_rows": 3}, force_full=False))
        self.assertTrue(bootstrap_required({"tracked_files": 1, "message_rows": 3}, force_full=True))
        self.assertTrue(indexes_ready_after_bootstrap(defer_heavy_indexes=True, bootstrap_mode=True, status_snapshot={}))
        self.assertTrue(indexes_ready_after_bootstrap(defer_heavy_indexes=True, bootstrap_mode=False, status_snapshot={}))
        self.assertTrue(indexes_ready_after_bootstrap(defer_heavy_indexes=False, bootstrap_mode=False, status_snapshot={}))

    def test_large_source_query_indexes_are_declared_in_maintenance_layer(self) -> None:
        light_sql = "\n".join(sql for _, sql in LIGHT_DUCKDB_INDEXES)
        heavy_sql = "\n".join(sql for _, sql in HEAVY_DUCKDB_INDEXES)

        self.assertIn("file_registry(file_name)", light_sql)
        self.assertIn("messages_raw(source_jsonl)", light_sql)
        self.assertIn("messages_raw(source_key)", light_sql)
        self.assertIn("file_registry(source_key)", light_sql)
        self.assertIn("messages_raw(source_jsonl, date_utc, message_id)", heavy_sql)
        self.assertIn("messages_raw(source_key, message_id)", heavy_sql)
        self.assertIn("messages_raw(source_key, date_utc_raw, message_id)", heavy_sql)
        self.assertIn("messages_raw(sender_username, sender_id)", heavy_sql)

    @unittest.skipIf(duckdb is None, "duckdb dependency is not installed")
    def test_schema_tracks_source_key_and_jsonl_duckdb_lag_columns(self) -> None:
        conn = duckdb.connect(":memory:")
        try:
            init_schema(conn)
            file_registry_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info('file_registry')").fetchall()
            }
            messages_raw_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info('messages_raw')").fetchall()
            }
        finally:
            conn.close()

        self.assertIn("source_key", file_registry_columns)
        self.assertIn("records_count_jsonl", file_registry_columns)
        self.assertIn("records_count_duckdb", file_registry_columns)
        self.assertIn("lag_rows", file_registry_columns)
        self.assertIn("source_key", messages_raw_columns)

    def test_duckdb_hot_path_queries_do_not_sort_by_python_timestamptz(self) -> None:
        root = Path(__file__).resolve().parents[1] / "app"
        checked_files = [
            root / "storage" / "duckdb_store.py",
            root / "services" / "media_assets.py",
            root / "services" / "contact_llm_runtime.py",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in checked_files)
        self.assertNotIn("coalesce(date_utc, TIMESTAMPTZ", combined)
        self.assertIn("coalesce(date_utc_raw, '')", combined)

    def test_source_file_stats_skips_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "b.jsonl"
            existing.write_text("{}", encoding="utf-8")
            missing = root / "missing.jsonl"
            rows = source_file_stats([missing, existing])

        self.assertEqual([row[0].name for row in rows], ["b.jsonl"])

    def test_connection_guard_reports_missing_dependency(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "duckdb dependency"):
            ensure_duckdb_available(None)
        self.assertIsNone(ensure_duckdb_available(object()))


if __name__ == "__main__":
    unittest.main()
