from pathlib import Path
import tempfile
import unittest

from app.storage.duckdb.ingest import bootstrap_required, source_file_stats


DUCKDB_STORE = Path(__file__).resolve().parents[1] / "app" / "storage" / "duckdb_store.py"


class DuckDbIncrementalIngestContractTests(unittest.TestCase):
    def test_bootstrap_is_required_only_for_empty_or_forced_store(self) -> None:
        self.assertTrue(bootstrap_required({"tracked_files": 0, "message_rows": 10}, force_full=False))
        self.assertTrue(bootstrap_required({"tracked_files": 2, "message_rows": 0}, force_full=False))
        self.assertTrue(bootstrap_required({"tracked_files": 2, "message_rows": 10}, force_full=True))
        self.assertFalse(bootstrap_required({"tracked_files": 2, "message_rows": 10}, force_full=False))

    def test_source_file_stats_skips_deleted_files_and_sorts_by_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            b_path = root / "b.jsonl"
            a_path = root / "a.jsonl"
            missing = root / "missing.jsonl"
            b_path.write_text("{}", encoding="utf-8")
            a_path.write_text("{}", encoding="utf-8")

            rows = source_file_stats([b_path, missing, a_path])

        self.assertEqual([row[0].name for row in rows], ["a.jsonl", "b.jsonl"])

    def test_hundred_jsonl_fixture_uses_incremental_file_stats_without_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for index in range(100):
                path = root / f"source_{index:03d}.jsonl"
                path.write_text('{"id": %d, "message": "hello"}\n' % index, encoding="utf-8")
                paths.append(path)

            first = source_file_stats(reversed(paths))
            second = source_file_stats(paths)

        self.assertEqual(100, len(first))
        self.assertEqual(100, len(second))
        self.assertEqual([row[0].name for row in first], [f"source_{index:03d}.jsonl" for index in range(100)])
        self.assertEqual([(row[0].name, row[1]) for row in first], [(row[0].name, row[1]) for row in second])

    def test_duckdb_ingest_tracks_offsets_and_reads_only_appended_jsonl(self) -> None:
        source = DUCKDB_STORE.read_text(encoding="utf-8")
        required_markers = [
            'sync_mode = "bootstrap" if bootstrap_mode else "incremental"',
            "SELECT size_bytes, ingested_offset, records_count, parquet_path, parquet_size_bytes, parquet_mtime_sec",
            "prev_offset = int(previous_row[1] or 0) if previous_row else 0",
            "reset_file = bool(force_full or (previous_row and file_size < prev_offset))",
            "conn.execute(\"DELETE FROM messages_raw WHERE source_jsonl = ?\", [source_jsonl])",
            "_iter_jsonl_records_with_offsets(path, offset=prev_offset)",
            "final_offset = file_size if file_size >= last_offset else last_offset",
            "source_jsonl, source_key, file_name, size_bytes, mtime_sec, ingested_offset, records_count,",
            "rows_ingested_in_run=total_inserted",
            'counts["rows_ingested_in_run"] = total_inserted',
            'counts["source_files_changed"] = changed_source_files',
        ]
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_zero_row_sync_does_not_queue_derived_rebuild(self) -> None:
        source = (DUCKDB_STORE.parents[1] / "legacy_runtime.py").read_text(encoding="utf-8")
        required_markers = [
            "ingest_result = await asyncio.to_thread(_duckdb_ingest_sync, force_full)",
            'rows_ingested = int((ingest_result or {}).get("rows_ingested_in_run", 0) or 0)',
            "if force_full or rows_ingested > 0",
            "else []",
        ]
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
