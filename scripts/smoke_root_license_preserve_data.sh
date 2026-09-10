#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_API="${ROOT_API:-http://127.0.0.1:8010}"
LICENSE_API="${LICENSE_API:-http://127.0.0.1:8015}"

cd "$ROOT_DIR"

if rg -n "down -v" \
  x-files-client-db docker-compose.yml backfront/backend/docker-compose.yml scripts \
  --glob '!docs/**' \
  --glob '!scripts/smoke_root_license_preserve_data.sh' >/tmp/xfiles-root-license-down-v.txt; then
  cat /tmp/xfiles-root-license-down-v.txt
  echo "root/license smoke refuses destructive docker compose down -v references outside docs" >&2
  exit 1
fi

test -d x-files-client-db/docker-data/root
test -d x-files-client-db/docker-data/root-postgres
test -d x-files-client-db/docker-data/license-server

root_response="$(curl -fsS "$ROOT_API/api/bootstrap")"
license_response="$(curl -fsS "$LICENSE_API/health")"
grep -q '"summary"' <<<"$root_response"
grep -q '"status"' <<<"$license_response"

echo "smoke_root_license_preserve_data: ok"
