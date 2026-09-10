"""Runtime filesystem paths used by the backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def default_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_DIR = Path(os.environ.get("PAYME_APP_DIR", str(default_app_dir()))).resolve()
PAYME_OUT_DIR = Path(os.environ.get("PAYME_OUT_DIR", str(APP_DIR / "out")))
LEGACY_PAYME_OUT_DIRS = [
    path.resolve()
    for path in [APP_DIR / "out2"]
    if path.exists() and path.resolve() != PAYME_OUT_DIR.resolve()
]
STATE_PATH = Path(os.environ.get("PAYME_STATE_PATH", str(APP_DIR / "state.json")))
CACHE_DIR = Path(os.environ.get("PAYME_CACHE_DIR", str(APP_DIR / "cache")))
DUCKDB_DIR = Path(os.environ.get("PAYME_DUCKDB_DIR", str(APP_DIR / "db" / "duckdb")))
DUCKDB_PATH = Path(os.environ.get("PAYME_DUCKDB_PATH", str(DUCKDB_DIR / "gramlead.duckdb")))
PARQUET_DIR = Path(os.environ.get("PAYME_PARQUET_DIR", str(APP_DIR / "db" / "parquet")))
JUR_ENTITIES_DIR = Path(os.environ.get("PAYME_JUR_ENTITIES_DIR", str(APP_DIR / "jur_entities")))
LEGACY_CACHE_ARCHIVE_DIR = Path(
    os.environ.get("PAYME_LEGACY_CACHE_ARCHIVE_DIR", str(APP_DIR / "db" / "legacy-cache-archive"))
)
LLM_TEMPLATE_PATH = Path(os.environ.get("PAYME_LLM_TEMPLATE_PATH", str(APP_DIR / "templates" / "default.tpl")))
LLM_SYSTEM_PROMPT_PATH = Path(
    os.environ.get(
        "PAYME_LLM_SYSTEM_PROMPT_PATH",
        str(APP_DIR / "prompts" / "button" / "gramlead" / "sys.md"),
    )
)
