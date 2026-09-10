#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/release_client_zips.sh [options]

Build official client ZIP releases through local x-files-root owner API.

Defaults:
  --win 1
  --mac 1
  --root-url http://127.0.0.1:8010
  --valid-until 2026-07-01
  --plan enterprise
  --output-root from x-files-client-db/docker-data/root/settings.json, or:
                /Volumes/t5/официальные релизы zip для клиентов

Options:
  --win N              Windows ZIP count. Use 0 to skip Windows.
  --mac N              macOS ZIP count. Use 0 to skip macOS.
  --valid-until DATE   License valid-until date, YYYY-MM-DD.
  --plan PLAN          License plan/tariff key.
  --root-url URL       Local owner UI URL.
  --output-root DIR    Root directory for official ZIP releases.
  --win-dir DIR        Exact Windows output directory.
  --mac-dir DIR        Exact macOS output directory.
  --settings FILE      Root settings JSON path.
  --poll-interval SEC  Job polling interval.
  --timeout SEC        Per-platform job timeout.
  --dry-run            Print JSON payloads and do not call API.
  -h, --help           Show this help.

Environment overrides:
  XFILES_RELEASE_WIN_COUNT
  XFILES_RELEASE_MAC_COUNT
  XFILES_RELEASE_VALID_UNTIL
  XFILES_RELEASE_PLAN
  XFILES_ROOT_WEB_URL
  XFILES_RELEASE_OUTPUT_ROOT
  XFILES_RELEASE_WIN_DIR
  XFILES_RELEASE_MAC_DIR
  XFILES_ROOT_SETTINGS

Root settings keys checked for output-root:
  official_release_zip_output_root, release_zip_output_root,
  client_release_output_root, bulk_release_output_root
USAGE
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_COUNT="${XFILES_RELEASE_WIN_COUNT:-1}"
MAC_COUNT="${XFILES_RELEASE_MAC_COUNT:-1}"
VALID_UNTIL="${XFILES_RELEASE_VALID_UNTIL:-2026-07-01}"
PLAN="${XFILES_RELEASE_PLAN:-enterprise}"
ROOT_URL="${XFILES_ROOT_WEB_URL:-http://127.0.0.1:8010}"
SETTINGS_FILE="${XFILES_ROOT_SETTINGS:-$ROOT_DIR/x-files-client-db/docker-data/root/settings.json}"
DEFAULT_OUTPUT_ROOT="/Volumes/t5/официальные релизы zip для клиентов"
OUTPUT_ROOT="${XFILES_RELEASE_OUTPUT_ROOT:-}"
WIN_DIR="${XFILES_RELEASE_WIN_DIR:-}"
MAC_DIR="${XFILES_RELEASE_MAC_DIR:-}"
POLL_INTERVAL="${XFILES_RELEASE_POLL_INTERVAL:-3}"
TIMEOUT_SECONDS="${XFILES_RELEASE_TIMEOUT_SECONDS:-7200}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --win)
      WIN_COUNT="${2:?--win requires a number}"
      shift 2
      ;;
    --mac)
      MAC_COUNT="${2:?--mac requires a number}"
      shift 2
      ;;
    --valid-until)
      VALID_UNTIL="${2:?--valid-until requires YYYY-MM-DD}"
      shift 2
      ;;
    --plan)
      PLAN="${2:?--plan requires a value}"
      shift 2
      ;;
    --root-url)
      ROOT_URL="${2:?--root-url requires URL}"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="${2:?--output-root requires directory}"
      shift 2
      ;;
    --win-dir)
      WIN_DIR="${2:?--win-dir requires directory}"
      shift 2
      ;;
    --mac-dir)
      MAC_DIR="${2:?--mac-dir requires directory}"
      shift 2
      ;;
    --settings)
      SETTINGS_FILE="${2:?--settings requires file path}"
      shift 2
      ;;
    --poll-interval)
      POLL_INTERVAL="${2:?--poll-interval requires seconds}"
      shift 2
      ;;
    --timeout)
      TIMEOUT_SECONDS="${2:?--timeout requires seconds}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_non_negative_int() {
  local name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "$name must be a non-negative integer, got: $value" >&2
    exit 2
  fi
}

require_non_negative_int "--win" "$WIN_COUNT"
require_non_negative_int "--mac" "$MAC_COUNT"
require_non_negative_int "--poll-interval" "$POLL_INTERVAL"
require_non_negative_int "--timeout" "$TIMEOUT_SECONDS"

if [[ "$WIN_COUNT" == "0" && "$MAC_COUNT" == "0" ]]; then
  echo "Nothing to build: --win 0 and --mac 0" >&2
  exit 2
fi

if [[ -z "$OUTPUT_ROOT" ]]; then
  OUTPUT_ROOT="$(
    /usr/bin/python3 - "$SETTINGS_FILE" "$DEFAULT_OUTPUT_ROOT" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
default = sys.argv[2]
keys = (
    "official_release_zip_output_root",
    "release_zip_output_root",
    "client_release_output_root",
    "bulk_release_output_root",
)
try:
    data = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
except Exception:
    data = {}
for key in keys:
    value = str(data.get(key) or "").strip()
    if value:
        print(value)
        break
else:
    print(default)
PY
  )"
fi

if [[ -z "$WIN_DIR" ]]; then
  WIN_DIR="$OUTPUT_ROOT/win"
fi
if [[ -z "$MAC_DIR" ]]; then
  MAC_DIR="$OUTPUT_ROOT/mac"
fi

PAYLOADS_JSON="$(
  /usr/bin/python3 - "$WIN_COUNT" "$MAC_COUNT" "$VALID_UNTIL" "$PLAN" "$WIN_DIR" "$MAC_DIR" <<'PY'
import json
import sys

win_count = int(sys.argv[1])
mac_count = int(sys.argv[2])
valid_until = sys.argv[3]
plan = sys.argv[4]
win_dir = sys.argv[5]
mac_dir = sys.argv[6]

payloads = []
output_dirs = {"windows": win_dir, "mac": mac_dir}
if win_count:
    payloads.append(
        {
            "platforms": ["windows"],
            "valid_until": valid_until,
            "count": win_count,
            "output_dirs": output_dirs,
            "plan": plan,
        }
    )
if mac_count:
    payloads.append(
        {
            "platforms": ["mac"],
            "valid_until": valid_until,
            "count": mac_count,
            "output_dirs": output_dirs,
            "plan": plan,
        }
    )
print(json.dumps(payloads, ensure_ascii=False, indent=2))
PY
)"

if [[ "$DRY_RUN" == "1" ]]; then
  printf '%s\n' "$PAYLOADS_JSON"
  exit 0
fi

/usr/bin/python3 - "$ROOT_URL" "$POLL_INTERVAL" "$TIMEOUT_SECONDS" "$PAYLOADS_JSON" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin
from typing import Optional

root_url = sys.argv[1].rstrip("/") + "/"
poll_interval = max(1, int(sys.argv[2]))
timeout_seconds = max(30, int(sys.argv[3]))
payloads = json.loads(sys.argv[4])


def request_json(method: str, path_or_url: str, payload: Optional[dict] = None) -> dict:
    url = path_or_url if path_or_url.startswith("http://") or path_or_url.startswith("https://") else urljoin(root_url, path_or_url.lstrip("/"))
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach {url}: {exc.reason}") from exc


def poll_job(status_url: str, label: str) -> dict:
    started = time.time()
    last_line = ""
    while True:
        snapshot = request_json("GET", status_url)
        job = snapshot.get("job") or {}
        status = str(job.get("status") or "unknown")
        percent = job.get("percent", 0)
        current_percent = job.get("current_percent", 0)
        current_status = job.get("current_status") or ""
        done = job.get("done", 0)
        total = job.get("total", 0)
        eta = job.get("total_eta_seconds", 0)
        line = f"{label}: {status} {percent}% total, current {current_percent}% · {done}/{total} · ETA {eta}s · {current_status}"
        if line != last_line:
            print(line, flush=True)
            last_line = line
        if status in {"completed", "completed_with_errors", "failed"}:
            return job
        if time.time() - started > timeout_seconds:
            raise SystemExit(f"{label}: timeout after {timeout_seconds}s")
        time.sleep(poll_interval)


all_results: list[dict] = []
for payload in payloads:
    platform_label = ",".join(payload.get("platforms") or [])
    count = payload.get("count")
    print(f"Starting release job: {platform_label} x {count}", flush=True)
    created = request_json("POST", "/api/licenses/bulk-release", payload)
    if not created.get("ok"):
        raise SystemExit(f"{platform_label}: failed to create job: {created}")
    job = poll_job(str(created.get("status_url") or ""), f"{platform_label} x {count}")
    all_results.extend(job.get("results") or [])
    if not job.get("ok"):
        print(json.dumps(job, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(f"{platform_label}: job finished with errors")

print("\nRelease ZIP results:")
print(json.dumps(all_results, ensure_ascii=False, indent=2))
PY
