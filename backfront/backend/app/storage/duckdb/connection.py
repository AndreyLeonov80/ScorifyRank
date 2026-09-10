"""DuckDB connection/dependency guards."""

from __future__ import annotations

from typing import Any


def ensure_duckdb_available(duckdb_module: Any) -> None:
    if duckdb_module is None:
        raise RuntimeError("duckdb dependency is not installed")
