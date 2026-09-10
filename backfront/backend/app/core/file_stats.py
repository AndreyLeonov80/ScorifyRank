"""Small filesystem counters used by runtime status and DuckDB maintenance."""

from __future__ import annotations

from pathlib import Path


def sum_glob_file_sizes(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    total = 0
    for path in directory.glob(pattern):
        try:
            if path.is_file():
                total += int(path.stat().st_size)
        except OSError:
            continue
    return total


def safe_file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size) if path.exists() and path.is_file() else 0
    except OSError:
        return 0


def count_glob_files(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    total = 0
    for path in directory.glob(pattern):
        try:
            if path.is_file():
                total += 1
        except OSError:
            continue
    return total
