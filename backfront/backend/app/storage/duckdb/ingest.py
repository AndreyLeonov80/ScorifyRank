"""DuckDB ingest planning helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def bootstrap_required(counts: Dict[str, int], *, force_full: bool) -> bool:
    return bool(
        force_full
        or int(counts.get("tracked_files", 0) or 0) <= 0
        or int(counts.get("message_rows", 0) or 0) <= 0
    )


def source_file_stats(paths: Iterable[Path]) -> List[Tuple[Path, object]]:
    rows: List[Tuple[Path, object]] = []
    for path in paths:
        try:
            rows.append((path, path.stat()))
        except FileNotFoundError:
            continue
    rows.sort(key=lambda item: str(item[0]))
    return rows

