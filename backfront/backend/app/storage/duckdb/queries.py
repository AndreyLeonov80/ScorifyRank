"""Small DuckDB query/result helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List


def lead_name_from_source_jsonl(source_jsonl: str) -> str:
    return Path(str(source_jsonl or "")).stem


def golden_counts_summary(counts: Dict[str, int]) -> Dict[str, int]:
    return {
        "tracked_files": int(counts.get("tracked_files", 0) or 0),
        "file_registry_rows": int(counts.get("file_registry_rows", 0) or 0),
        "message_rows": int(counts.get("message_rows", 0) or 0),
        "source_files_indexed": int(counts.get("source_files_indexed", 0) or 0),
    }


def golden_last_messages(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "source_jsonl": str(row.get("source_jsonl") or ""),
                "message_id": int(row.get("message_id") or 0),
                "text": str(row.get("text") or ""),
                "date_utc_raw": str(row.get("date_utc_raw") or ""),
            }
        )
    return sorted(normalized, key=lambda item: (item["source_jsonl"], item["message_id"]))

