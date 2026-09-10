#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8009}"
FRONT_URL="${FRONT_URL:-http://127.0.0.1:8008}"

retry() {
  local attempt=1
  local max_attempts=10
  until "$@"; do
    if [ "$attempt" -ge "$max_attempts" ]; then
      return 1
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
}

check_front() {
  curl --max-time 8 -sSI "$FRONT_URL/dashboard.html" | grep -q "200 OK"
}

check_api() {
  curl --max-time 12 -sS "$API_URL/api/payme/dashboard/summary?limit=5" \
    | /usr/bin/python3 -c '
import json
import sys

data = json.load(sys.stdin)
sources = data.get("scanned_sources") or {}
totals = sources.get("totals") or {}
assert "items" in sources, "scanned_sources.items missing"
assert isinstance(sources.get("items"), list), "scanned_sources.items is not a list"
assert "selected_sources" in totals, "selected_sources total missing"
assert "messages_count" in totals, "messages_count total missing"
print("dashboard_source_stats_http: ok total={} messages={}".format(sources.get("total", 0), totals.get("messages_count", 0)))
'
}

retry check_front
retry check_api
