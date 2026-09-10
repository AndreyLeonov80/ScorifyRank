"""Runtime configuration for the optimized backend layout.

The legacy `back.py` module still reads many environment variables directly.
This module is the migration target: new routers and services should depend on
`settings` instead of calling `os.environ` inline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return str(os.environ.get(name) or default).strip()


@dataclass(frozen=True)
class BackendSettings:
    web_port: int
    state_path: Path
    out_dir: Path
    cache_dir: Path
    duckdb_dir: Path
    parquet_dir: Path
    jur_entities_dir: Path
    frontend_origin: str
    openrouter_timeout_sec: float
    ocr_request_timeout_sec: float

    @classmethod
    def from_env(cls) -> BackendSettings:
        return cls(
            web_port=int(_env("WEB_PORT", "8009")),
            state_path=Path(_env("PAYME_STATE_PATH", "/data/state/state.json")),
            out_dir=Path(_env("PAYME_OUT_DIR", "/data/out")),
            cache_dir=Path(_env("PAYME_CACHE_DIR", "/data/cache")),
            duckdb_dir=Path(_env("PAYME_DUCKDB_DIR", "/data/db/duckdb")),
            parquet_dir=Path(_env("PAYME_PARQUET_DIR", "/data/db/parquet")),
            jur_entities_dir=Path(_env("PAYME_JUR_ENTITIES_DIR", "/data/jur_entities")),
            frontend_origin=_env("X_FILES_FRONTEND_ORIGIN", "http://127.0.0.1:8008"),
            openrouter_timeout_sec=float(_env("PAYME_OPENROUTER_TIMEOUT_SEC", "300")),
            ocr_request_timeout_sec=float(_env("PAYME_OCR_TIMEOUT_SEC", "600")),
        )


settings = BackendSettings.from_env()
