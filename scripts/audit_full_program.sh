#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backfront/backend"
FRONTEND_DIR="$ROOT_DIR/backfront/frontend"

echo "[1/4] Backend contract tests"
cd "$BACKEND_DIR"
/usr/bin/python3 -m pytest \
  tests/test_preflight_report.py \
  tests/test_source_stats_contract.py \
  tests/test_source_lookup_cache.py \
  tests/test_dashboard_source_counts.py \
  tests/test_contact_llm_split.py \
  tests/test_runtime_config_contract.py \
  tests/test_legacy_runtime_split_file_stats.py \
  tests/test_grid_limits_persistence.py \
  tests/test_source_delete_cascade.py \
  tests/test_error_taxonomy_runtime_logs.py \
  tests/test_api_response_shape.py \
  tests/test_state_save_atomic_fallback.py \
  tests/test_duckdb_incremental_ingest.py \
  tests/test_duckdb_lock_concurrent_writer.py \
  tests/test_jobs_progress_eta.py \
  tests/test_import_dialog_membership_filters.py \
  tests/test_data_source_plugins.py \
  tests/test_duckdb_store_split.py \
  tests/test_telegram_sync_runtime_split.py \
  tests/test_jobs_queue_contract.py \
  tests/test_x_files_local_license.py \
  tests/test_x_files_root_web_prefill.py \
  tests/test_x_files_license_server_privacy.py \
  tests/test_xfiles_deals_engine_split.py

cd "$ROOT_DIR"
/usr/bin/python3 scripts/audit_code_size_budgets.py

echo "[2/4] Frontend typecheck"
cd "$FRONTEND_DIR"
npm run typecheck

echo "[3/4] Frontend build"
npm run build

echo "[4/4] Frontend audits"
npm run audit:api-client-errors
npm run audit:api-cache-dedupe
npm run audit:data-source-plugins
npm run audit:failed-fetch-fallback
npm run audit:frontend-smoke-pages
npm run smoke:playwright-pages
npm run audit:frontend-state-snapshots
npm run audit:dashboard-source-stats
npm run audit:dashboard-lean
npm run audit:grid-source-stats
npm run audit:heavy-http-pages
npm run audit:import-buttons
npm run audit:paged-source-tables
npm run audit:polling-budget
npm run audit:release-version
npm run audit:ts-refactor
npm run audit:lazy-pages
npm run audit:legacy-store-split
npm run audit:scss
npm run audit:silent-errors
npm run audit:shared-components
npm run audit:ui-state-persistence
npm run audit:import-progress-popup
npm run audit:index-chat-ui-large-data
npm run audit:virtualized-lists
npm run audit:index-chat-prompts-and-paging
npm run audit:startup-license-filters
npm run audit:js-size

echo "OK: full local audit passed"
