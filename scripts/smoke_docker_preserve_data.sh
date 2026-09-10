#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${API_BASE:-http://127.0.0.1:8008}"

cd "$ROOT_DIR"

docker-compose ps >/tmp/xfiles-docker-compose-ps.txt
grep -q "x-files-client-db" /tmp/xfiles-docker-compose-ps.txt
grep -q "x-files-backfront-new-back" /tmp/xfiles-docker-compose-ps.txt

preflight="$(curl -fsS "$API_BASE/api/payme/preflight-report")"
echo "$preflight" | grep -q '"state"'
echo "$preflight" | grep -q '"duckdb"'
echo "$preflight" | grep -q '"jsonl"'
echo "$preflight" | grep -q '"telethon"'

source_stats="$(curl -fsS "$API_BASE/api/payme/source-stats?page=1&page_size=1")"
echo "$source_stats" | grep -q '"items"'
echo "$source_stats" | grep -q '"summary"'

echo "smoke_docker_preserve_data: ok"
