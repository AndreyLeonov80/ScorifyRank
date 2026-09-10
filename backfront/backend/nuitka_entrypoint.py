#!/usr/bin/env python3
"""Nuitka runtime entrypoint for the X-Files client backend.

This file is copied only into the builder stage. The production image should
run the compiled binary produced from this entrypoint, not this source file.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn


os.environ.setdefault("PAYME_APP_DIR", "/app")

from app.main import app  # noqa: E402  # The app reads env paths during import.


def ensure_runtime_dirs() -> None:
    paths = [
        Path(os.environ.get("PAYME_STATE_PATH", "/data/state/state.json")).parent,
        Path(os.environ.get("PAYME_OUT_DIR", "/data/out")),
        Path(os.environ.get("PAYME_CACHE_DIR", "/data/cache")),
        Path(os.environ.get("PAYME_DUCKDB_DIR", "/data/db/duckdb")),
        Path(os.environ.get("PAYME_PARQUET_DIR", "/data/db/parquet")),
        Path(os.environ.get("PAYME_JUR_ENTITIES_DIR", "/data/jur_entities")),
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

    state_path = Path(os.environ.get("PAYME_STATE_PATH", "/data/state/state.json"))
    if not state_path.exists():
        state_path.write_text("{}\n", encoding="utf-8")


def main() -> None:
    ensure_runtime_dirs()
    web_port = int(os.environ.get("WEB_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=web_port)


if __name__ == "__main__":
    main()
