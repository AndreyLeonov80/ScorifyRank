"""Local signed invite-license and persisted license-state helpers.

The module is intentionally dependency-free so the same code can run in
`x-files-client-backfront`, `x-files-root` tests, and future Nuitka builds.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


LICENSE_SCHEMA = "x-files-license/v1"
LICENSE_STATE_SCHEMA = "x-files-license-state/v1"
ACTIVATION_RECEIPT_SCHEMA = "x-files-activation-receipt/v1"
METADATA_BACKUP_SCHEMA = "x-files-metadata-backup/v1"
MIGRATION_AUDIT_SCHEMA = "x-files-migration-audit/v1"
DEFAULT_GRACE_DAYS = 3
DEFAULT_CLOCK_SKEW_SECONDS = 300
DEFAULT_LICENSE_TOUCH_INTERVAL_SECONDS = 60


@dataclass
class LicenseError(RuntimeError):
    """Raised when a signed license or local state cannot be trusted."""

    message: str

    def __str__(self) -> str:
        return self.message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def parse_version_tuple(value: str | None) -> tuple[int, ...]:
    """Extract a comparable numeric tuple from release labels.

    Release labels in this project are usually calendar-like
    `2026.05.08-test`, but invite-codes can also contain simple semver labels.
    We intentionally compare numeric chunks only so suffixes like `-test` do not
    make local/offline entitlement checks brittle.
    """

    chunks = [int(item) for item in re.findall(r"\d+", str(value or ""))]
    if not chunks:
        return tuple()
    while len(chunks) < 3:
        chunks.append(0)
    return tuple(chunks)


def compare_versions(left: str | None, right: str | None) -> int:
    left_tuple = parse_version_tuple(left)
    right_tuple = parse_version_tuple(right)
    max_len = max(len(left_tuple), len(right_tuple))
    left_tuple = left_tuple + (0,) * (max_len - len(left_tuple))
    right_tuple = right_tuple + (0,) * (max_len - len(right_tuple))
    if left_tuple < right_tuple:
        return -1
    if left_tuple > right_tuple:
        return 1
    return 0


def validate_version_entitlement(license_payload: dict[str, Any], app_version: str | None) -> dict[str, Any]:
    """Validate whether the running app version is allowed by this license."""

    app_version = str(app_version or "").strip()
    version_min = str(license_payload.get("version_min") or "").strip()
    version_max = str(license_payload.get("version_max") or "").strip()
    if not app_version:
        return {
            "checked": False,
            "app_version": "",
            "version_min": version_min,
            "version_max": version_max,
        }
    if version_min and parse_version_tuple(version_min) and compare_versions(app_version, version_min) < 0:
        raise LicenseError(f"App version {app_version} is older than license minimum {version_min}")
    if version_max and parse_version_tuple(version_max) and compare_versions(app_version, version_max) > 0:
        raise LicenseError(f"App version {app_version} is newer than license maximum {version_max}")
    return {
        "checked": True,
        "app_version": app_version,
        "version_min": version_min,
        "version_max": version_max,
    }


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    if not secret:
        raise LicenseError("License signing secret is empty")
    return hmac.new(secret.encode("utf-8"), json_dumps(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def sign_payload_urlsafe(payload: dict[str, Any], secret: str) -> str:
    """Return the root-bundle signature format used by x-files-root manifests."""

    if not secret:
        raise LicenseError("License signing secret is empty")
    digest = hmac.new(secret.encode("utf-8"), json_dumps(payload).encode("utf-8"), hashlib.sha256).digest()
    import base64

    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_signed_document(document: dict[str, Any], secret: str, *, expected_schema: str | None = None) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise LicenseError("Signed document must be a JSON object")
    payload = document.get("payload")
    signature = str(document.get("signature") or "")
    if not isinstance(payload, dict) or not signature:
        raise LicenseError("Signed document must contain payload and signature")
    if expected_schema and payload.get("schema") != expected_schema:
        raise LicenseError(f"Unexpected license schema: {payload.get('schema')}")
    expected_hex = sign_payload(payload, secret)
    expected_root = sign_payload_urlsafe(payload, secret)
    if not (hmac.compare_digest(signature, expected_hex) or hmac.compare_digest(signature, expected_root)):
        raise LicenseError("Signed document signature mismatch")
    return payload


def load_signed_license(path: str | Path, secret: str) -> dict[str, Any]:
    license_path = Path(path)
    if not license_path.exists():
        raise LicenseError(f"Invite license does not exist: {license_path}")
    try:
        document = json.loads(license_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LicenseError(f"Invite license is not valid JSON: {exc}") from exc
    return verify_signed_document(document, secret, expected_schema=LICENSE_SCHEMA)


def build_instance_hash(instance_id: str | None = None, *, salt: str | None = None) -> str:
    """Build a stable one-device hash without storing raw machine details in license-server.

    In Docker delivery `APP_INSTANCE_ID` should be generated into `.env` once and
    persisted with the client's data. Hostname and machine-id are best-effort
    stabilizers for local/offline installs, not customer data.
    """

    raw = {
        "instance_id": instance_id or os.environ.get("APP_INSTANCE_ID", ""),
        "hostname": socket.gethostname(),
        "machine_id": _read_first_existing(["/etc/machine-id", "/var/lib/dbus/machine-id"]),
        "salt": salt or os.environ.get("XFILES_INSTANCE_SALT", "x-files-client"),
    }
    return hashlib.sha256(json_dumps(raw).encode("utf-8")).hexdigest()


def mask_secret(value: str, *, visible_prefix: int = 6, visible_suffix: int = 4) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= visible_prefix + visible_suffix:
        return raw[:2] + "…" if len(raw) > 2 else "…"
    return f"{raw[:visible_prefix]}…{raw[-visible_suffix:]}"


def _read_first_existing(paths: list[str]) -> str:
    for raw_path in paths:
        path = Path(raw_path)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip()
            except Exception:
                return ""
    return ""


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _signed_state_document(state_payload: dict[str, Any], signing_secret: str) -> dict[str, Any]:
    return {
        "payload": state_payload,
        "signature_alg": "HMAC-SHA256",
        "signature": sign_payload(state_payload, signing_secret),
    }


def _write_signed_state(path: str | Path, state_payload: dict[str, Any], signing_secret: str) -> None:
    _atomic_write_json(Path(path), _signed_state_document(state_payload, signing_secret))


def _state_last_seen_at(state: dict[str, Any] | None) -> datetime | None:
    if not state:
        return None
    for key in ("last_seen_at", "last_status_checked_at", "last_applied_at", "activated_at"):
        parsed = parse_iso(str(state.get(key) or ""))
        if parsed:
            return parsed
    return None


def _assert_no_clock_rollback(
    state: dict[str, Any] | None,
    *,
    now: datetime,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
) -> None:
    last_seen = _state_last_seen_at(state)
    if not last_seen:
        return
    allowed_skew = timedelta(seconds=max(0, int(clock_skew_seconds)))
    if now + allowed_skew < last_seen:
        raise LicenseError(
            "System clock rollback detected: "
            f"current time {to_iso(now)} is earlier than trusted last_seen_at {to_iso(last_seen)}"
        )


def _touch_license_state_if_needed(
    *,
    state_path: str | Path,
    signing_secret: str,
    state: dict[str, Any],
    now: datetime,
    touch_interval_seconds: int = DEFAULT_LICENSE_TOUCH_INTERVAL_SECONDS,
) -> dict[str, Any]:
    last_seen = _state_last_seen_at(state)
    interval = timedelta(seconds=max(0, int(touch_interval_seconds)))
    if last_seen and now <= last_seen + interval:
        return state
    touched = dict(state)
    touched["last_seen_at"] = to_iso(now)
    touched["last_status_checked_at"] = to_iso(now)
    _write_signed_state(state_path, touched, signing_secret)
    return touched


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_archive_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return normalized or "metadata"


def validate_schema_compatibility(
    current_schema_version: int | str | None,
    *,
    min_supported: int | str | None = None,
    max_supported: int | str | None = None,
) -> dict[str, Any]:
    """Validate that persisted metadata can be used by this app version."""

    try:
        current = int(current_schema_version)
    except Exception as exc:
        raise LicenseError("Current schema version is not a valid integer") from exc
    min_value = int(min_supported) if min_supported not in {None, ""} else None
    max_value = int(max_supported) if max_supported not in {None, ""} else None
    if min_value is not None and current < min_value:
        raise LicenseError(f"Schema version {current} is older than supported minimum {min_value}")
    if max_value is not None and current > max_value:
        raise LicenseError(f"Schema version {current} is newer than supported maximum {max_value}")
    return {
        "checked": True,
        "current_schema_version": current,
        "min_supported": min_value,
        "max_supported": max_value,
    }


def create_metadata_backup(
    metadata_paths: dict[str, str | Path],
    *,
    backup_dir: str | Path,
    reason: str = "before-migration",
    now: datetime | None = None,
    app_version: str | None = None,
    schema_version: int | str | None = None,
) -> dict[str, Any]:
    """Create a ZIP backup of small metadata files before risky updates.

    This helper intentionally accepts files only. Telegram jsonl archives,
    DuckDB databases, CRM exports and other customer datasets should live in
    persistent volumes and must not be silently copied by a metadata backup.
    """

    now = now or utc_now()
    if not isinstance(metadata_paths, dict) or not metadata_paths:
        raise LicenseError("Metadata backup requires at least one metadata file")

    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    backup_path = backup_root / f"x-files-metadata-{timestamp}.zip"
    if backup_path.exists():
        backup_path = backup_root / f"x-files-metadata-{timestamp}-{os.getpid()}.zip"

    files: list[dict[str, Any]] = []
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for key, raw_path in sorted(metadata_paths.items()):
            source_path = Path(raw_path)
            if not source_path.exists():
                continue
            if not source_path.is_file():
                raise LicenseError(f"Metadata backup accepts files only: {source_path}")
            content = source_path.read_bytes()
            archive_name = f"metadata/{_safe_archive_name(str(key))}-{_safe_archive_name(source_path.name)}"
            archive.writestr(archive_name, content)
            files.append(
                {
                    "key": str(key),
                    "source_path": str(source_path),
                    "archive_path": archive_name,
                    "bytes": len(content),
                    "sha256": _sha256_bytes(content),
                }
            )
        manifest = {
            "schema": METADATA_BACKUP_SCHEMA,
            "created_at": to_iso(now),
            "reason": str(reason or ""),
            "app_version": str(app_version or ""),
            "schema_version": str(schema_version or ""),
            "files": files,
        }
        archive.writestr("metadata-backup-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    return {
        "ok": True,
        "schema": METADATA_BACKUP_SCHEMA,
        "backup_path": str(backup_path),
        "created_at": to_iso(now),
        "reason": str(reason or ""),
        "file_count": len(files),
        "files": files,
    }


def restore_metadata_backup(
    backup_path: str | Path,
    *,
    target_paths: dict[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Restore metadata files from a backup without deleting user data."""

    resolved_backup = Path(backup_path)
    if not resolved_backup.exists():
        raise LicenseError(f"Metadata backup does not exist: {resolved_backup}")
    target_paths = target_paths if isinstance(target_paths, dict) else {}
    restored: list[dict[str, Any]] = []

    with zipfile.ZipFile(resolved_backup) as archive:
        try:
            manifest = json.loads(archive.read("metadata-backup-manifest.json").decode("utf-8"))
        except Exception as exc:
            raise LicenseError(f"Metadata backup manifest is invalid: {exc}") from exc
        if manifest.get("schema") != METADATA_BACKUP_SCHEMA:
            raise LicenseError(f"Unexpected metadata backup schema: {manifest.get('schema')}")
        for item in manifest.get("files") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            archive_name = str(item.get("archive_path") or "")
            if not key or not archive_name:
                continue
            content = archive.read(archive_name)
            expected_sha = str(item.get("sha256") or "")
            if expected_sha and not hmac.compare_digest(_sha256_bytes(content), expected_sha):
                raise LicenseError(f"Metadata backup checksum mismatch for {key}")
            target = Path(target_paths.get(key) or item.get("source_path") or "")
            if not str(target):
                raise LicenseError(f"Metadata restore target is missing for {key}")
            _atomic_write_bytes(target, content)
            restored.append(
                {
                    "key": key,
                    "target_path": str(target),
                    "bytes": len(content),
                    "sha256": _sha256_bytes(content),
                }
            )

    return {
        "ok": True,
        "schema": METADATA_BACKUP_SCHEMA,
        "backup_path": str(resolved_backup),
        "restored_count": len(restored),
        "restored": restored,
    }


def build_migration_audit_record(
    *,
    action: str,
    ok: bool,
    migration: str,
    from_schema: int | str | None = None,
    to_schema: int | str | None = None,
    backup_path: str | Path | None = None,
    app_version: str | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a migration audit record with metadata only, no customer rows."""

    now = now or utc_now()
    return {
        "schema": MIGRATION_AUDIT_SCHEMA,
        "ts": to_iso(now),
        "action": str(action or ""),
        "ok": bool(ok),
        "migration": str(migration or ""),
        "from_schema": str(from_schema or ""),
        "to_schema": str(to_schema or ""),
        "backup_path": str(backup_path or ""),
        "app_version": str(app_version or ""),
        "error": str(error or ""),
        "details": details if isinstance(details, dict) else {},
    }


def append_migration_audit_record(path: str | Path, record: dict[str, Any]) -> None:
    audit_path = Path(path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_migration_audit_records(path: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    audit_path = Path(path)
    if not audit_path.exists():
        return []
    limit = max(1, min(int(limit or 50), 500))
    rows: list[dict[str, Any]] = []
    try:
        lines = audit_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in reversed(lines):
        if len(rows) >= limit:
            break
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def build_license_server_activation_payload(
    license_payload: dict[str, Any],
    *,
    instance_hash: str,
    version: str | None = None,
    invite_code: str = "",
) -> dict[str, Any]:
    """Return the privacy-safe payload sent to x-files-license-server.

    The license server must never receive Telegram messages, CRM rows, deals,
    media OCR text, DuckDB rows, or any other customer business data.
    """

    return {
        "license_id": license_payload.get("license_id"),
        "license_token": license_payload.get("license_token"),
        "client_id": license_payload.get("client_id"),
        "instance_hash": instance_hash,
        "device_hash": instance_hash,
        "client_email": license_payload.get("client_email"),
        "activation_key": license_payload.get("activation_key"),
        "activation_duration_days": license_payload.get("activation_duration_days"),
        "invite_batch_id": license_payload.get("invite_batch_id"),
        "invite_code_required": bool(license_payload.get("invite_code_required", False)),
        "invite_code": invite_code.strip(),
        "plan": license_payload.get("plan"),
        "version": version or license_payload.get("release"),
        "max_activations": int(license_payload.get("max_activations") or 1),
        "limits": license_payload.get("limits") if isinstance(license_payload.get("limits"), dict) else {},
        "features": license_payload.get("features") if isinstance(license_payload.get("features"), dict) else {},
        "allowed_menus": license_payload.get("allowed_menus") if isinstance(license_payload.get("allowed_menus"), list) else [],
        "disabled_menus": license_payload.get("disabled_menus") if isinstance(license_payload.get("disabled_menus"), list) else [],
    }


def verify_license_server_online(
    license_payload: dict[str, Any],
    *,
    instance_hash: str,
    server_url: str | None = None,
    timeout_seconds: float = 3.0,
    urlopen: Callable[..., Any] | None = None,
    invite_code: str = "",
) -> dict[str, Any]:
    """Best-effort online license-server check.

    A reachable license-server can reject revoked licenses or second-device
    activations. If the server is unavailable, `offline_allowed=true` keeps the
    local offline activation path working.
    """

    resolved_url = str(
        server_url
        or license_payload.get("license_server_url")
        or os.environ.get("XFILES_LICENSE_SERVER_URL")
        or ""
    ).strip()
    if not resolved_url:
        return {"ok": True, "online": False, "status": "skipped", "reason": "no_license_server_url"}

    if license_payload.get("invite_code_required") and not invite_code.strip():
        raise LicenseError("Invite code is required for this universal release")

    payload = build_license_server_activation_payload(license_payload, instance_hash=instance_hash, invite_code=invite_code)
    request = urllib.request.Request(
        resolved_url.rstrip("/") + "/api/license/activate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urlopen or urllib.request.urlopen
    offline_allowed = bool(license_payload.get("offline_allowed", False)) and not bool(license_payload.get("invite_code_required"))

    try:
        with opener(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = f"License server rejected invite-code: HTTP {exc.code} {detail}".strip()
        if exc.code in {400, 403, 409, 422, 429}:
            raise LicenseError(message) from exc
        if offline_allowed:
            return {"ok": True, "online": False, "status": "server_error_offline_allowed", "error": message}
        raise LicenseError(message) from exc
    except Exception as exc:
        message = f"License server is unavailable: {exc}"
        if offline_allowed:
            return {"ok": True, "online": False, "status": "offline_allowed", "error": message}
        raise LicenseError(f"{message}; offline activation is not allowed") from exc

    try:
        parsed = json.loads(body) if body.strip() else {}
    except Exception:
        parsed = {"raw": body}
    status = str(parsed.get("status") or "ok") if isinstance(parsed, dict) else "ok"
    if status in {"revoked", "blocked", "denied"}:
        raise LicenseError(f"License server rejected invite-code: {status}")
    return {"ok": True, "online": True, "status": status, "response": parsed}


def apply_license_server_authority(license_payload: dict[str, Any], online_status: dict[str, Any] | None) -> dict[str, Any]:
    """Overlay local entitlement with the authoritative license-server response."""

    if not isinstance(online_status, dict) or not online_status.get("online"):
        return license_payload
    response = online_status.get("response")
    if not isinstance(response, dict):
        return license_payload
    patched = dict(license_payload)
    expires_at = str(response.get("expires_at") or "").strip()
    if expires_at:
        patched["valid_until"] = expires_at
    for key in ("limits", "features"):
        if isinstance(response.get(key), dict):
            patched[key] = response[key]
    for key in ("allowed_menus", "disabled_menus"):
        if isinstance(response.get(key), list):
            patched[key] = response[key]
    if response.get("max_activations") is not None:
        patched["max_activations"] = int(response.get("max_activations") or 1)
    return patched


def _license_server_status_url(status_payload: dict[str, Any], server_url: str | None = None) -> str:
    resolved_url = str(
        server_url
        or (status_payload.get("license_server") if isinstance(status_payload.get("license_server"), dict) else {}).get("url")
        or status_payload.get("license_server_url")
        or os.environ.get("XFILES_LICENSE_SERVER_URL")
        or ""
    ).strip()
    license_id = str(status_payload.get("license_id") or "").strip()
    if not resolved_url or not license_id:
        return ""
    return f"{resolved_url.rstrip('/')}/api/license/status/{urllib.parse.quote(license_id)}"


def refresh_license_server_status(
    status_payload: dict[str, Any],
    *,
    server_url: str | None = None,
    timeout_seconds: float = 3.0,
    urlopen: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Overlay local license-state with owner-side license-server status.

    This is intentionally read-only for local state: owner renew/revoke must be
    visible immediately in the runtime status without mutating customer data.
    """

    if not isinstance(status_payload, dict):
        return status_payload
    url = _license_server_status_url(status_payload, server_url=server_url)
    if not url:
        return status_payload
    opener = urlopen or urllib.request.urlopen
    refreshed = dict(status_payload)
    license_server = dict(refreshed.get("license_server") if isinstance(refreshed.get("license_server"), dict) else {})
    license_server["url"] = str(server_url or license_server.get("url") or os.environ.get("XFILES_LICENSE_SERVER_URL") or "")
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with opener(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
        data = json.loads(body) if body.strip() else {}
    except Exception as exc:
        license_server.update({"online": False, "status": "unavailable", "error": str(exc)})
        refreshed["license_server"] = license_server
        refreshed.update(
            {
                "ok": False,
                "status": "license_server_unavailable",
                "message": "License-server is unavailable.",
                "read_only": True,
                "disabled_reason": "Нет связи с license-server. Доступ к функциям заблокирован до восстановления проверки лицензии.",
            }
        )
        return refreshed

    if not isinstance(data, dict):
        license_server.update({"online": False, "status": "invalid_response", "error": "license-server returned non-object"})
        refreshed["license_server"] = license_server
        refreshed.update(
            {
                "ok": False,
                "status": "license_server_invalid_response",
                "message": "License-server returned invalid response.",
                "read_only": True,
                "disabled_reason": "License-server вернул некорректный ответ. Доступ к функциям заблокирован до корректной проверки лицензии.",
            }
        )
        return refreshed

    server_status = str(data.get("status") or "active").strip() or "active"
    license_server.update(
        {
            "online": True,
            "status": server_status,
            "error": "",
            "server_time": str(data.get("server_time") or ""),
            "expires_at": str(data.get("expires_at") or ""),
        }
    )
    refreshed["license_server"] = license_server

    if server_status in {"revoked", "blocked", "denied"}:
        refreshed.update(
            {
                "ok": False,
                "status": "revoked",
                "message": "Лицензия отозвана владельцем продукта.",
                "read_only": True,
                "disabled_reason": "Лицензия отозвана владельцем продукта. Обратитесь к владельцу для продления или повторного включения.",
            }
        )
        return refreshed
    if server_status == "expired":
        refreshed.update(
            {
                "ok": False,
                "status": "expired",
                "message": "Срок лицензии истёк по данным license-server.",
                "read_only": True,
                "disabled_reason": "Срок лицензии истёк по данным license-server. Требуется продление владельцем продукта.",
            }
        )
    elif server_status in {"active", "ok"}:
        refreshed["status"] = "active"
        refreshed["ok"] = True
        refreshed["read_only"] = False
        refreshed["disabled_reason"] = ""
        refreshed["message"] = "License is valid"
    else:
        refreshed.update(
            {
                "ok": False,
                "status": server_status,
                "message": f"License-server status is not active: {server_status}",
                "read_only": True,
                "disabled_reason": "Лицензия не активна по данным license-server. Доступ к функциям заблокирован.",
            }
        )

    expires_at = str(data.get("expires_at") or "").strip()
    if expires_at:
        refreshed["valid_until"] = expires_at
    for key in ("limits", "features"):
        if isinstance(data.get(key), dict):
            refreshed[key] = data[key]
    for key in ("allowed_menus", "disabled_menus"):
        if isinstance(data.get(key), list):
            refreshed[key] = data[key]
    if data.get("max_activations") is not None:
        refreshed["max_activations"] = int(data.get("max_activations") or 1)
    if data.get("activation_count") is not None:
        refreshed["activation_count"] = int(data.get("activation_count") or 0)
    return refreshed


def _state_payload_from_license(
    license_payload: dict[str, Any],
    *,
    instance_hash: str,
    existing_state: dict[str, Any] | None = None,
    applied_at: datetime | None = None,
    app_version: str | None = None,
    version_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    applied_at = applied_at or utc_now()
    existing_last_seen = _state_last_seen_at(existing_state)
    last_seen_at = applied_at
    if existing_last_seen and existing_last_seen > last_seen_at:
        last_seen_at = existing_last_seen
    history = []
    if existing_state and isinstance(existing_state.get("history"), list):
        history = [item for item in existing_state["history"] if isinstance(item, dict)]
    history.append(
        {
            "applied_at": to_iso(applied_at),
            "license_id": license_payload.get("license_id"),
            "license_kind": license_payload.get("license_kind", "activation"),
            "plan": license_payload.get("plan"),
            "release": license_payload.get("release"),
        }
    )
    activation_duration_days = 0
    try:
        activation_duration_days = int(license_payload.get("activation_duration_days") or 0)
    except Exception:
        activation_duration_days = 0
    valid_from_value = license_payload.get("valid_from")
    valid_until_value = license_payload.get("valid_until")
    duration_days_value = license_payload.get("duration_days")
    activation_started_at = existing_state.get("activation_started_at") if existing_state else ""
    if activation_duration_days > 0:
        same_license = bool(existing_state and existing_state.get("license_id") == license_payload.get("license_id"))
        existing_activation_started = str(existing_state.get("activation_started_at") or "") if existing_state else ""
        if same_license and existing_activation_started:
            started_at = parse_iso(existing_activation_started) or applied_at
            activation_started_at = existing_activation_started
            valid_from_value = existing_state.get("valid_from") or to_iso(started_at)
            valid_until_value = existing_state.get("valid_until") or to_iso(started_at + timedelta(days=activation_duration_days))
            duration_days_value = existing_state.get("duration_days") or activation_duration_days
        else:
            activation_started_at = to_iso(applied_at)
            valid_from_value = to_iso(applied_at)
            valid_until_value = to_iso(applied_at + timedelta(days=activation_duration_days))
            duration_days_value = activation_duration_days
    return {
        "schema": LICENSE_STATE_SCHEMA,
        "license_id": license_payload.get("license_id"),
        "client_id": license_payload.get("client_id"),
        "client_email": license_payload.get("client_email"),
        "root_email": license_payload.get("root_email"),
        "plan": license_payload.get("plan"),
        "plan_title": license_payload.get("plan_title"),
        "release": license_payload.get("release"),
        "app_version": app_version or (existing_state.get("app_version") if existing_state else "") or "",
        "version_min": license_payload.get("version_min") or "",
        "version_max": license_payload.get("version_max") or "",
        "update_channel": license_payload.get("update_channel") or "",
        "version_check": version_check if isinstance(version_check, dict) else {},
        "first_seen_at": existing_state.get("first_seen_at") if existing_state else to_iso(applied_at),
        "activated_at": existing_state.get("activated_at") if existing_state else to_iso(applied_at),
        "last_applied_at": to_iso(applied_at),
        "last_seen_at": to_iso(last_seen_at),
        "last_status_checked_at": existing_state.get("last_status_checked_at") if existing_state else "",
        "valid_from": valid_from_value,
        "valid_until": valid_until_value,
        "duration_days": duration_days_value,
        "activation_duration_days": activation_duration_days,
        "activation_started_at": activation_started_at,
        "offline_allowed": bool(license_payload.get("offline_allowed", False)),
        "hardware_binding_policy": license_payload.get("hardware_binding_policy", "one_device"),
        "max_activations": int(license_payload.get("max_activations") or 1),
        "limits": license_payload.get("limits") if isinstance(license_payload.get("limits"), dict) else {},
        "features": license_payload.get("features") if isinstance(license_payload.get("features"), dict) else {},
        "allowed_menus": license_payload.get("allowed_menus") if isinstance(license_payload.get("allowed_menus"), list) else [],
        "disabled_menus": license_payload.get("disabled_menus") if isinstance(license_payload.get("disabled_menus"), list) else [],
        "instance_hash": instance_hash,
        "history": history[-200:],
    }


def load_license_state(path: str | Path, secret: str) -> dict[str, Any] | None:
    state_path = Path(path)
    if not state_path.exists():
        return None
    try:
        document = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LicenseError(f"License state is not valid JSON: {exc}") from exc
    return verify_signed_document(document, secret, expected_schema=LICENSE_STATE_SCHEMA)


def apply_license(
    license_document: dict[str, Any],
    *,
    state_path: str | Path,
    signing_secret: str,
    instance_hash: str | None = None,
    now: datetime | None = None,
    online_check: bool = False,
    license_server_url: str | None = None,
    online_timeout_seconds: float = 3.0,
    urlopen: Callable[..., Any] | None = None,
    invite_code: str = "",
    app_version: str | None = None,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
) -> dict[str, Any]:
    """Verify an invite-license and persist a signed local license-state."""

    license_payload = verify_signed_document(license_document, signing_secret, expected_schema=LICENSE_SCHEMA)
    instance_hash = instance_hash or build_instance_hash()
    now = now or utc_now()
    existing_state = load_license_state(state_path, signing_secret)
    _assert_no_clock_rollback(existing_state, now=now, clock_skew_seconds=clock_skew_seconds)
    if existing_state:
        existing_hash = existing_state.get("instance_hash")
        if existing_hash and existing_hash != instance_hash:
            raise LicenseError("License state is already bound to another instance")
        existing_license = existing_state.get("license_id")
        license_kind = str(license_payload.get("license_kind") or "activation")
        if existing_license and existing_license != license_payload.get("license_id") and license_kind == "activation":
            raise LicenseError("Activation license cannot replace existing license-state; use renewal or upgrade")
        if license_kind in {"renewal", "upgrade", "addon", "update", "support", "trial-extension"}:
            existing_client_id = str(existing_state.get("client_id") or "")
            new_client_id = str(license_payload.get("client_id") or "")
            if existing_client_id and new_client_id and existing_client_id != new_client_id:
                raise LicenseError("Invite-code belongs to another client")
    else:
        license_kind = str(license_payload.get("license_kind") or "activation")
        if license_kind == "update":
            raise LicenseError("Update invite-code requires an existing activated license-state")

    valid_from = parse_iso(str(license_payload.get("valid_from") or ""))
    valid_until = parse_iso(str(license_payload.get("valid_until") or ""))
    if valid_from and now < valid_from - timedelta(minutes=5):
        raise LicenseError("Invite license is not active yet")
    try:
        activation_duration_days = int(license_payload.get("activation_duration_days") or 0)
    except Exception:
        activation_duration_days = 0
    if valid_until and activation_duration_days <= 0 and now > valid_until + timedelta(days=DEFAULT_GRACE_DAYS):
        raise LicenseError("Invite license is expired")

    version_check = validate_version_entitlement(license_payload, app_version)

    online_status: dict[str, Any] | None = None
    if online_check:
        online_status = verify_license_server_online(
            license_payload,
            instance_hash=instance_hash,
            server_url=license_server_url,
            timeout_seconds=online_timeout_seconds,
            urlopen=urlopen,
            invite_code=invite_code,
        )
        license_payload = apply_license_server_authority(license_payload, online_status)

    state_payload = _state_payload_from_license(
        license_payload,
        instance_hash=instance_hash,
        existing_state=existing_state,
        applied_at=now,
        app_version=app_version,
        version_check=version_check,
    )
    if online_status:
        state_payload["license_server"] = {
            "online": bool(online_status.get("online")),
            "status": str(online_status.get("status") or ""),
            "checked_at": to_iso(now),
            "error": str(online_status.get("error") or ""),
            "server_time": str((online_status.get("response") or {}).get("server_time") or ""),
            "trusted_time": str((online_status.get("response") or {}).get("trusted_time") or ""),
            "expires_at": str((online_status.get("response") or {}).get("expires_at") or ""),
        }
    if invite_code.strip():
        state_payload["invite_code"] = invite_code.strip()
    _write_signed_state(state_path, state_payload, signing_secret)
    return state_payload


def license_status(
    *,
    state_path: str | Path,
    signing_secret: str,
    now: datetime | None = None,
    grace_days: int = DEFAULT_GRACE_DAYS,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    touch_interval_seconds: int = DEFAULT_LICENSE_TOUCH_INTERVAL_SECONDS,
) -> dict[str, Any]:
    now = now or utc_now()
    try:
        state = load_license_state(state_path, signing_secret)
    except LicenseError as exc:
        return {
            "ok": False,
            "status": "tampered",
            "message": str(exc),
            "read_only": True,
            "disabled_reason": "Лицензия повреждена или не прошла проверку подписи. Платные функции отключены.",
        }
    if not state:
        return {
            "ok": False,
            "status": "missing",
            "message": "License state is missing",
            "read_only": True,
            "disabled_reason": "Лицензия ещё не активирована. Доступны только стартовые действия и экран активации.",
        }

    try:
        _assert_no_clock_rollback(state, now=now, clock_skew_seconds=clock_skew_seconds)
    except LicenseError as exc:
        return {
            "ok": False,
            "status": "clock_tampered",
            "message": str(exc),
            "read_only": True,
            "disabled_reason": (
                "Обнаружен откат системного времени. Платные функции отключены до восстановления "
                "корректной даты/времени или онлайн-проверки лицензии."
            ),
            "license_id": state.get("license_id"),
            "client_email": state.get("client_email"),
            "plan": state.get("plan"),
            "plan_title": state.get("plan_title"),
            "valid_until": state.get("valid_until"),
            "last_seen_at": state.get("last_seen_at"),
            "clock_status": "rollback_detected",
        }

    state = _touch_license_state_if_needed(
        state_path=state_path,
        signing_secret=signing_secret,
        state=state,
        now=now,
        touch_interval_seconds=touch_interval_seconds,
    )

    valid_until = parse_iso(str(state.get("valid_until") or ""))
    grace_until: datetime | None = None
    days_remaining: int | None = None
    in_grace = False
    status = "active"
    if valid_until:
        seconds = (valid_until - now).total_seconds()
        days_remaining = int(seconds // 86400)
        if now > valid_until:
            grace_until = valid_until + timedelta(days=grace_days)
            if now <= grace_until:
                status = "grace"
                in_grace = True
            else:
                status = "expired"
    read_only = status == "expired"
    if status == "active":
        message = "License is valid"
        disabled_reason = ""
    elif status == "grace":
        grace_suffix = f" до {to_iso(grace_until)}" if grace_until else ""
        message = f"Срок тарифа истёк, действует grace period{grace_suffix}."
        disabled_reason = ""
    else:
        message = (
            "Срок тарифа истёк. Платные функции переведены в read-only/disabled режим: "
            "данные сохраняются, но сбор, анализ и экспорт требуют продления тарифа."
        )
        disabled_reason = message

    return {
        "ok": status in {"active", "grace"},
        "status": status,
        "message": message,
        "read_only": read_only,
        "disabled_reason": disabled_reason,
        "license_id": state.get("license_id"),
        "client_email": state.get("client_email"),
        "plan": state.get("plan"),
        "plan_title": state.get("plan_title"),
        "release": state.get("release"),
        "app_version": state.get("app_version"),
        "version_min": state.get("version_min"),
        "version_max": state.get("version_max"),
        "update_channel": state.get("update_channel"),
        "version_check": state.get("version_check") if isinstance(state.get("version_check"), dict) else {},
        "valid_until": state.get("valid_until"),
        "grace_until": to_iso(grace_until) if grace_until else None,
        "days_remaining": days_remaining,
        "in_grace": in_grace,
        "limits": state.get("limits") if isinstance(state.get("limits"), dict) else {},
        "features": state.get("features") if isinstance(state.get("features"), dict) else {},
        "allowed_menus": state.get("allowed_menus") if isinstance(state.get("allowed_menus"), list) else [],
        "disabled_menus": state.get("disabled_menus") if isinstance(state.get("disabled_menus"), list) else [],
        "activated_at": state.get("activated_at"),
        "last_applied_at": state.get("last_applied_at"),
        "last_seen_at": state.get("last_seen_at"),
        "invite_batch_id": state.get("invite_batch_id"),
        "invite_code_required": bool(state.get("invite_code_required", False)),
        "invite_code_masked": mask_secret(str(state.get("invite_code") or "")),
        "license_kind": state.get("license_kind"),
        "max_activations": state.get("max_activations"),
        "activation_count": state.get("activation_count"),
        "clock_status": "ok",
        "history_count": len(state.get("history") or []),
        "license_server": state.get("license_server") if isinstance(state.get("license_server"), dict) else {},
    }


def build_activation_receipt(
    *,
    state_path: str | Path,
    signing_secret: str,
    app_version: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a privacy-safe activation receipt for x-files-root.

    The receipt intentionally contains only license metadata. It must not carry
    Telegram messages, CRM rows, deals, OCR text, jsonl snippets, or analytics
    rows from the customer installation.
    """

    now = now or utc_now()
    state = load_license_state(state_path, signing_secret)
    if not state:
        raise LicenseError("License state is missing")
    payload = {
        "schema": ACTIVATION_RECEIPT_SCHEMA,
        "created_at": to_iso(now),
        "license_id": state.get("license_id"),
        "client_id": state.get("client_id"),
        "client_email": state.get("client_email"),
        "plan": state.get("plan"),
        "plan_title": state.get("plan_title"),
        "release": state.get("release"),
        "app_version": app_version or state.get("release") or "",
        "activated_at": state.get("activated_at"),
        "last_applied_at": state.get("last_applied_at"),
        "valid_until": state.get("valid_until"),
        "limits": state.get("limits") if isinstance(state.get("limits"), dict) else {},
        "features": state.get("features") if isinstance(state.get("features"), dict) else {},
        "allowed_menus": state.get("allowed_menus") if isinstance(state.get("allowed_menus"), list) else [],
        "disabled_menus": state.get("disabled_menus") if isinstance(state.get("disabled_menus"), list) else [],
        "instance_hash": state.get("instance_hash"),
    }
    return {
        "payload": payload,
        "signature_alg": "HMAC-SHA256",
        "signature": sign_payload(payload, signing_secret),
    }


def _license_payload_from_document(document: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(document, dict):
        return {}
    payload = document.get("payload")
    if isinstance(payload, dict):
        return payload
    return document


def build_license_audit_record(
    *,
    action: str,
    ok: bool,
    document: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
    error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a small audit record without storing the raw signed invite body."""

    now = now or utc_now()
    payload = _license_payload_from_document(document)
    status = status if isinstance(status, dict) else {}
    return {
        "ts": to_iso(now),
        "action": str(action or ""),
        "ok": bool(ok),
        "license_kind": str(payload.get("license_kind") or ""),
        "license_id": str(payload.get("license_id") or status.get("license_id") or ""),
        "client_id": str(payload.get("client_id") or ""),
        "client_email": str(payload.get("client_email") or status.get("client_email") or ""),
        "plan": str(payload.get("plan") or status.get("plan") or ""),
        "plan_title": str(payload.get("plan_title") or status.get("plan_title") or ""),
        "release": str(payload.get("release") or status.get("release") or ""),
        "valid_until": str(payload.get("valid_until") or status.get("valid_until") or ""),
        "status": str(status.get("status") or ""),
        "message": str(status.get("message") or ""),
        "error": str(error or ""),
    }


def append_license_audit_record(path: str | Path, record: dict[str, Any]) -> None:
    audit_path = Path(path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_license_audit_records(path: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    audit_path = Path(path)
    if not audit_path.exists():
        return []
    limit = max(1, min(int(limit or 50), 500))
    rows: list[dict[str, Any]] = []
    try:
        lines = audit_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in reversed(lines):
        if len(rows) >= limit:
            break
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def compute_effective_allowed_menus(
    status: dict[str, Any] | None,
    known_menus: list[str],
    *,
    fallback_menus: list[str] | None = None,
) -> dict[str, Any]:
    """Return menu keys allowed by current license-state.

    Missing/inactive license is fail-soft: only fallback menus are shown so the
    user can open Dashboard/Tariffs/Settings and activate or repair the license.
    Active license with empty `allowed_menus` means "all known menus".
    """

    status = status if isinstance(status, dict) else {}
    known = [str(item) for item in known_menus if str(item or "").strip()]
    fallback = [str(item) for item in (fallback_menus or []) if str(item or "").strip()]
    disabled = {
        str(item).strip()
        for item in status.get("disabled_menus", [])
        if str(item or "").strip()
    } if isinstance(status.get("disabled_menus"), list) else set()

    if not status.get("ok"):
        allowed = [item for item in fallback if item not in disabled]
        return {
            "enforced": False,
            "effective_allowed_menus": allowed,
            "disabled_menus": sorted(disabled),
            "fallback": True,
        }

    explicit_allowed = [
        str(item).strip()
        for item in status.get("allowed_menus", [])
        if str(item or "").strip()
    ] if isinstance(status.get("allowed_menus"), list) else []
    source = explicit_allowed or known
    source_set = set(source)
    allowed = [item for item in known if item in source_set and item not in disabled]
    return {
        "enforced": True,
        "effective_allowed_menus": allowed,
        "disabled_menus": sorted(disabled),
        "fallback": False,
    }
