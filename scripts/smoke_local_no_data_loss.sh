#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/backfront/backend"
/usr/bin/python3 -m unittest tests.test_data_source_plugins
/usr/bin/python3 -m unittest \
  tests.test_app_router_extraction.BackendRouterExtractionTest.test_data_sources_router_declares_data_source_endpoint_paths \
  tests.test_app_router_extraction.BackendRouterExtractionTest.test_app_main_prefers_extracted_data_source_routes

cd "$ROOT_DIR/backfront/frontend"
npm run typecheck
npm run audit:data-source-plugins
npm run audit:dashboard-source-stats

echo "smoke_local_no_data_loss: ok"
