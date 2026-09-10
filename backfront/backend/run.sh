#!/usr/bin/env sh
set -eu

APP_DIR="/app"
STATE_PATH="${PAYME_STATE_PATH:-/data/state/state.json}"
OUT_DIR="${PAYME_OUT_DIR:-/data/out}"
CACHE_DIR="${PAYME_CACHE_DIR:-/data/cache}"
DUCKDB_DIR="${PAYME_DUCKDB_DIR:-/data/db/duckdb}"
PARQUET_DIR="${PAYME_PARQUET_DIR:-/data/db/parquet}"
JUR_ENTITIES_DIR="${PAYME_JUR_ENTITIES_DIR:-/data/jur_entities}"
WEB_PORT="${WEB_PORT:-8001}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"

export PAYME_STATE_PATH="${STATE_PATH}"
export PAYME_OUT_DIR="${OUT_DIR}"
export PAYME_CACHE_DIR="${CACHE_DIR}"
export PAYME_DUCKDB_DIR="${DUCKDB_DIR}"
export PAYME_DUCKDB_PATH="${PAYME_DUCKDB_PATH:-${DUCKDB_DIR}/gramlead.duckdb}"
export PAYME_PARQUET_DIR="${PARQUET_DIR}"
export PAYME_JUR_ENTITIES_DIR="${JUR_ENTITIES_DIR}"

mkdir -p \
  "$(dirname "${STATE_PATH}")" \
  "${OUT_DIR}" \
  "${CACHE_DIR}" \
  "${DUCKDB_DIR}" \
  "${PARQUET_DIR}" \
  "${JUR_ENTITIES_DIR}"

if [ ! -f "${STATE_PATH}" ]; then
  printf '%s\n' '{}' > "${STATE_PATH}"
fi

if [ "${UVICORN_WORKERS}" -gt 1 ]; then
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${WEB_PORT}" --workers "${UVICORN_WORKERS}"
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${WEB_PORT}"
