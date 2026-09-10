import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests


if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parent
SECRET_ENV = "APP_LICENSE_SECRET"
INTEGRITY_ENV = "APP_INTEGRITY_MANIFEST"
INSTANCE_ENV = "APP_INSTANCE_ID"
TIME_SERVER_URL_ENV = "APP_TIME_SERVER_URL"
DEFAULT_TIME_SERVER_URL = "https://www.google.com/generate_204"
LICENSE_DIR = Path(os.environ.get("APP_LICENSE_DIR", str(Path.home() / ".app_license_store")))
LICENSE_MIRROR_DIR_RAW = os.environ.get("APP_LICENSE_MIRROR_DIR", "").strip()
MAX_RUNS = int(os.environ.get("APP_LICENSE_MAX_RUNS", "100"))
EXPIRE_DATE = datetime.fromisoformat(
    os.environ.get("APP_LICENSE_EXPIRE_AT", "2026-05-01T00:00:00+00:00")
).astimezone(timezone.utc)
MAX_CLOCK_SKEW_SECONDS = int(os.environ.get("APP_LICENSE_CLOCK_SKEW_SEC", "300"))
TIME_SERVER_TIMEOUT_SECONDS = float(os.environ.get("APP_TIME_SERVER_TIMEOUT_SEC", "5"))

LICENSE_STORAGE_DIRS = [LICENSE_DIR]
if LICENSE_MIRROR_DIR_RAW:
    LICENSE_STORAGE_DIRS.append(Path(LICENSE_MIRROR_DIR_RAW))

LICENSE_FILES = [directory / "license.dat" for directory in LICENSE_STORAGE_DIRS] + [
    directory / ".license.bak" for directory in LICENSE_STORAGE_DIRS
]
MARKER_FILES = [directory / "install.marker" for directory in LICENSE_STORAGE_DIRS] + [
    directory / ".install.bak" for directory in LICENSE_STORAGE_DIRS
]
CRITICAL_FILES = {
    "back.py": APP_ROOT / "back.py",
    "security.py": APP_ROOT / "security.py",
}


class LicenseNetworkError(RuntimeError):
    pass


def _fail(message: str) -> None:
    print(message)
    sys.exit(1)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def get_trusted_time() -> datetime:
    time_server_url = os.environ.get(TIME_SERVER_URL_ENV, "").strip() or DEFAULT_TIME_SERVER_URL
    if not time_server_url:
        _fail(f"{TIME_SERVER_URL_ENV} is not set")

    last_error: Optional[Exception] = None
    for method in ("HEAD", "GET"):
        try:
            response = requests.request(
                method=method,
                url=time_server_url,
                allow_redirects=True,
                timeout=TIME_SERVER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            date_header = response.headers.get("Date", "").strip()
            if not date_header:
                raise ValueError("Date header is missing")

            parsed = parsedate_to_datetime(date_header)
            return parsed.astimezone(timezone.utc)
        except Exception as exc:
            last_error = exc

    raise LicenseNetworkError(f"Trusted time request failed: {last_error}")


def _get_secret_key() -> bytes:
    secret = os.environ.get(SECRET_ENV, "").strip()
    if not secret:
        _fail(f"{SECRET_ENV} is not set")
    return secret.encode("utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _json_dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_data(data: bytes) -> bytes:
    return hmac.new(_get_secret_key(), data, hashlib.sha256).digest()


def encode(payload: dict) -> str:
    raw = _json_dumps(payload)
    signature = sign_data(raw)
    return base64.b64encode(raw + signature).decode("utf-8")


def decode(token: str) -> dict:
    decoded = base64.b64decode(token.encode("utf-8"))
    raw = decoded[:-32]
    signature = decoded[-32:]

    if not hmac.compare_digest(signature, sign_data(raw)):
        raise ValueError("Tampered data")

    return json.loads(raw.decode("utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _can_migrate_fingerprint() -> bool:
    return bool(getattr(sys, "frozen", False) and os.environ.get(INSTANCE_ENV, "").strip())


def build_integrity_manifest() -> str:
    payload = {
        "generated_at": _to_iso(_now_utc()),
        "files": {
            name: _sha256_file(path)
            for name, path in CRITICAL_FILES.items()
        },
    }
    return encode(payload)


def verify_integrity() -> None:
    token = os.environ.get(INTEGRITY_ENV, "").strip()
    if not token:
        return

    try:
        payload = decode(token)
    except Exception:
        _fail("Integrity manifest is invalid")

    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        _fail("Integrity manifest is empty")

    for name, expected_hash in files.items():
        path = CRITICAL_FILES.get(name)
        if path is None or not path.exists():
            _fail(f"Critical file is missing: {name}")

        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            _fail(f"Application integrity check failed: {name}")


def _read_machine_id() -> str:
    candidates = [
        Path("/etc/machine-id"),
        Path("/var/lib/dbus/machine-id"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return _read_text(path).strip()
            except Exception:
                continue
    return ""


def get_runtime_fingerprint() -> str:
    payload = {
        "instance_id": os.environ.get(INSTANCE_ENV, ""),
        "hostname": socket.gethostname(),
        "machine_id": _read_machine_id(),
        "app_root": str(APP_ROOT),
    }
    return hashlib.sha256(_json_dumps(payload)).hexdigest()


def _read_token(path: Path) -> Optional[dict]:
    if not path.exists():
        return None

    try:
        raw = _read_text(path).strip()
        if not raw:
            return None
        return decode(raw)
    except Exception:
        return None


def _write_token(paths: List[Path], payload: dict) -> None:
    token = encode(payload)
    for path in paths:
        _write_text(path, token)


def _load_markers() -> List[dict]:
    markers: List[dict] = []
    for path in MARKER_FILES:
        payload = _read_token(path)
        if payload:
            markers.append(payload)
    return markers


def _load_records() -> List[dict]:
    records: List[dict] = []
    for path in LICENSE_FILES:
        payload = _read_token(path)
        if payload:
            records.append(payload)
    return records


def _select_latest_payload(payloads: List[dict]) -> dict:
    def sort_key(payload: dict):
        last_seen = payload.get("last_seen_at") or payload.get("created_at") or "1970-01-01T00:00:00+00:00"
        return (
            int(payload.get("runs", 0)),
            _parse_iso(last_seen).timestamp(),
            _parse_iso(payload.get("created_at", "1970-01-01T00:00:00+00:00")).timestamp(),
        )

    return max(payloads, key=sort_key)


def _validate_marker_payload(marker: dict, fingerprint: str) -> None:
    if marker.get("fingerprint") != fingerprint:
        if not _can_migrate_fingerprint():
            _fail("Environment fingerprint mismatch")
        marker["fingerprint"] = fingerprint
    if not marker.get("install_id"):
        _fail("Install marker is invalid")


def _ensure_marker(fingerprint: str, now: datetime) -> dict:
    markers = _load_markers()
    if not markers:
        marker = {
            "install_id": secrets.token_hex(16),
            "fingerprint": fingerprint,
            "created_at": _to_iso(now),
        }
        _write_token(MARKER_FILES, marker)
        return marker

    marker = _select_latest_payload(markers)
    _validate_marker_payload(marker, fingerprint)

    install_id = marker["install_id"]
    for item in markers:
        _validate_marker_payload(item, fingerprint)
        if item["install_id"] != install_id:
            _fail("Install marker mismatch detected")

    _write_token(MARKER_FILES, marker)
    return marker


def _build_initial_license(marker: dict, now: datetime) -> dict:
    now_iso = _to_iso(now)
    return {
        "install_id": marker["install_id"],
        "fingerprint": marker["fingerprint"],
        "created_at": marker["created_at"],
        "last_seen_at": now_iso,
        "runs": 0,
    }


def load_license_state(marker: dict, now: datetime) -> dict:
    records = _load_records()
    if not records:
        return _build_initial_license(marker, now)

    record = _select_latest_payload(records)
    if record.get("fingerprint") != marker["fingerprint"]:
        if not _can_migrate_fingerprint():
            _fail("License fingerprint mismatch")
        record["fingerprint"] = marker["fingerprint"]
    if record.get("install_id") != marker["install_id"]:
        _fail("License install id mismatch")
    if not isinstance(record.get("runs"), int) or record["runs"] < 0:
        _fail("License counter is invalid")
    if "last_seen_at" not in record or "created_at" not in record:
        _fail("License record is incomplete")
    return record


def save_license_state(data: dict) -> None:
    _write_token(LICENSE_FILES, data)


def check_license() -> None:
    verify_integrity()

    now = get_trusted_time()
    fingerprint = get_runtime_fingerprint()
    marker_exists = any(path.exists() for path in MARKER_FILES)
    license_exists = any(path.exists() for path in LICENSE_FILES)

    marker = _ensure_marker(fingerprint, now)
    data = load_license_state(marker, now)

    if marker_exists and not license_exists:
        _fail("License state was removed")

    last_seen = _parse_iso(data["last_seen_at"])
    if now.timestamp() + MAX_CLOCK_SKEW_SECONDS < last_seen.timestamp():
        _fail("System time rollback detected")

    if now > EXPIRE_DATE:
        _fail("License expired - contact developer")

    runs = int(data.get("runs", 0))
    if runs >= MAX_RUNS:
        _fail("Run limit exceeded - contact developer")

    data["last_seen_at"] = _to_iso(now if now > last_seen else last_seen)
    data["runs"] = runs + 1
    save_license_state(data)


def _main(argv: List[str]) -> int:
    if len(argv) > 1 and argv[1] == "manifest":
        print(build_integrity_manifest())
        return 0

    if len(argv) > 1 and argv[1] == "check":
        try:
            check_license()
            print("license-ok")
            return 0
        except LicenseNetworkError as exc:
            print(str(exc))
            return 1

    print("Usage: python security.py [manifest|check]")
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
