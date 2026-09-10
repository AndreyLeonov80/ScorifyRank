from __future__ import annotations

from app.core import file_stats
import app.legacy_runtime as legacy_runtime


def test_legacy_runtime_uses_split_file_stats_helpers() -> None:
    assert legacy_runtime._sum_glob_file_sizes is file_stats.sum_glob_file_sizes
    assert legacy_runtime._safe_file_size is file_stats.safe_file_size
    assert legacy_runtime._count_glob_files is file_stats.count_glob_files
