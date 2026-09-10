"""License, menu entitlement, and local import limit helpers for the legacy runtime."""

from __future__ import annotations

import base64
import hashlib
import hmac
import imaplib
import json
import logging
import os
import re
import smtplib
import socket
import ssl
import sys
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime") or sys.modules.get("back")
    if runtime is None:
        return
    for name, value in vars(runtime).items():
        if not name.startswith("__") and name != "refresh_legacy_globals":
            globals()[name] = value


def _with_legacy_globals(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        refresh_legacy_globals()
        return func(*args, **kwargs)

    return wrapper


refresh_legacy_globals()

CLIENT_EMAIL_SECRET_SCHEMA = "x-files-client-email-secret/v1"
XFILES_LOCAL_OWNER_VALID_UNTIL = "2099-01-01T23:59:59+00:00"


def _client_email_secret_key() -> bytes:
    seed = str(
        os.environ.get("XFILES_CLIENT_SETTINGS_SECRET")
        or os.environ.get("XFILES_LICENSE_SIGNING_SECRET")
        or socket.gethostname()
        or "x-files-client-settings"
    )
    return hashlib.sha256(f"x-files-client-email:{seed}".encode("utf-8")).digest()


def _client_email_secret_stream(length: int, *, salt: bytes) -> bytes:
    key = _client_email_secret_key()
    chunks: List[bytes] = []
    counter_value = 0
    while sum(len(chunk) for chunk in chunks) < length:
        counter_value += 1
        chunks.append(
            hmac.new(
                key,
                salt + counter_value.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
    return b"".join(chunks)[:length]


def _encrypt_client_email_password(value: str) -> Dict[str, str]:
    plain = str(value or "").encode("utf-8")
    if not plain:
        return {}
    salt = os.urandom(16)
    stream = _client_email_secret_stream(len(plain), salt=salt)
    cipher = bytes(a ^ b for a, b in zip(plain, stream))
    return {
        "schema": CLIENT_EMAIL_SECRET_SCHEMA,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "ciphertext": base64.urlsafe_b64encode(cipher).decode("ascii"),
    }


def _decrypt_client_email_password(secret: Any) -> str:
    if not _client_email_password_configured(secret):
        return ""
    try:
        salt = base64.urlsafe_b64decode(str(secret.get("salt") or "").encode("ascii"))
        cipher = base64.urlsafe_b64decode(str(secret.get("ciphertext") or "").encode("ascii"))
        stream = _client_email_secret_stream(len(cipher), salt=salt)
        plain = bytes(a ^ b for a, b in zip(cipher, stream))
        return plain.decode("utf-8")
    except Exception:
        return ""


def _client_email_password_configured(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("schema") == CLIENT_EMAIL_SECRET_SCHEMA
        and bool(value.get("salt"))
        and bool(value.get("ciphertext"))
    )




def _openrouter_timeout_sec() -> float:
    try:
        settings = _get_app_settings()
        value = float(settings.get("openrouter_timeout_sec", OPENROUTER_REQUEST_TIMEOUT_SEC))
    except Exception:
        value = OPENROUTER_REQUEST_TIMEOUT_SEC
    return min(300.0, max(5.0, value))






def _xfiles_license_dir() -> Path:
    return Path(os.environ.get("APP_LICENSE_DIR") or "/data/license")


def _xfiles_license_state_path() -> Path:
    return Path(os.environ.get("XFILES_LICENSE_STATE_PATH") or (_xfiles_license_dir() / "license-state.json"))


def _xfiles_invite_license_path() -> Path:
    return Path(os.environ.get("XFILES_LICENSE_FILE") or (_xfiles_license_dir() / "invite-license.json"))


def _xfiles_invite_code_path() -> Path:
    return Path(os.environ.get("XFILES_INVITE_CODE_FILE") or (_xfiles_license_dir() / "INVITE-CODE.md"))


def _xfiles_license_audit_path() -> Path:
    return Path(os.environ.get("XFILES_LICENSE_AUDIT_PATH") or (_xfiles_license_dir() / "license-audit.jsonl"))


def _xfiles_release_manifest_path() -> Path:
    return Path(os.environ.get("XFILES_RELEASE_MANIFEST_PATH") or (APP_DIR / "release-manifest.json"))


def _xfiles_local_owner_days_remaining() -> int:
    try:
        valid_until = datetime.fromisoformat(XFILES_LOCAL_OWNER_VALID_UNTIL)
        return max(0, (valid_until.date() - datetime.now(timezone.utc).date()).days)
    except Exception:
        return 0


def _xfiles_client_delivery_mode() -> bool:
    raw = str(os.environ.get("XFILES_CLIENT_DELIVERY") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("XFILES_RELEASE_VERSION") and _xfiles_release_manifest_path().exists())


def _xfiles_license_signing_secret() -> str:
    return str(
        os.environ.get("XFILES_LICENSE_SIGNING_SECRET")
        or os.environ.get("XFILES_ROOT_SIGNING_SECRET")
        or ""
    ).strip()


def _xfiles_manifest_signing_secret() -> str:
    return str(
        os.environ.get("XFILES_RELEASE_SIGNING_SECRET")
        or os.environ.get("XFILES_ROOT_SIGNING_SECRET")
        or ""
    ).strip()


def _xfiles_compact_json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _xfiles_verify_root_signature(payload: Dict[str, Any], signature: str, secret: str) -> bool:
    digest = hmac.new(secret.encode("utf-8"), _xfiles_compact_json_bytes(payload), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return hmac.compare_digest(str(signature or ""), expected)


def _xfiles_update_status_payload() -> Dict[str, Any]:
    manifest_path = _xfiles_release_manifest_path()
    release = str(os.environ.get("XFILES_RELEASE_VERSION") or "").strip()
    image = str(os.environ.get("XFILES_BACKFRONT_IMAGE") or "").strip()
    result: Dict[str, Any] = {
        "ok": False,
        "status": "manifest_missing",
        "message": "release-manifest.json не найден рядом с поставкой.",
        "release": release,
        "channel": str(os.environ.get("XFILES_RELEASE_CHANNEL") or "local").strip() or "local",
        "image": image,
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "manifest_signed": False,
        "manifest_verified": False,
        "manifest_sha256": "",
        "image_digests": {},
        "image_refs": {},
    }
    if not manifest_path.exists():
        return result

    try:
        raw = manifest_path.read_bytes()
        result["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
        document = json.loads(raw.decode("utf-8"))
        payload = document.get("payload") if isinstance(document, dict) else None
        signature = str(document.get("signature") or "") if isinstance(document, dict) else ""
        if not isinstance(payload, dict):
            result.update(
                {
                    "status": "manifest_invalid",
                    "message": "release-manifest.json найден, но структура payload некорректна.",
                }
            )
            return result

        result["release"] = str(payload.get("release") or release or "")
        result["image_digests"] = payload.get("image_digests") if isinstance(payload.get("image_digests"), dict) else {}
        result["image_refs"] = payload.get("image_refs") if isinstance(payload.get("image_refs"), dict) else {}
        result["manifest_signed"] = bool(signature)
        secret = _xfiles_manifest_signing_secret()
        if signature and secret:
            verified = _xfiles_verify_root_signature(payload, signature, secret)
            result.update(
                {
                    "ok": verified,
                    "status": "verified" if verified else "signature_mismatch",
                    "message": "Update manifest проверен по подписи." if verified else "Подпись update manifest не совпадает.",
                    "manifest_verified": verified,
                }
            )
        elif signature:
            result.update(
                {
                    "ok": True,
                    "status": "signed",
                    "message": "Update manifest подписан; локальный секрет проверки не задан.",
                }
            )
        else:
            result.update(
                {
                    "status": "unsigned",
                    "message": "Update manifest найден, но не подписан.",
                }
            )
        return result
    except Exception as exc:
        result.update(
            {
                "status": "manifest_error",
                "message": f"Не удалось прочитать update manifest: {exc}",
            }
        )
        return result


def _xfiles_raw_app_settings() -> Dict[str, Any]:
    sync = globals().get("telegram_sync")
    if sync is not None and isinstance(getattr(sync, "state", None), dict):
        maybe = sync.state.get(globals().get("APP_SETTINGS_STATE_KEY", "_app_settings"))
        if isinstance(maybe, dict):
            return maybe
    state_path = globals().get("STATE_PATH")
    if isinstance(state_path, Path) and state_path.exists():
        try:
            state_payload = json.loads(state_path.read_text(encoding="utf-8", errors="replace"))
            maybe = state_payload.get(globals().get("APP_SETTINGS_STATE_KEY", "_app_settings")) if isinstance(state_payload, dict) else None
            if isinstance(maybe, dict):
                return maybe
        except Exception:
            pass
    return {}


def _xfiles_local_import_limit_value(settings: Dict[str, Any], key: str, default: int) -> int:
    if bool(settings.get("telegram_unlimited_import_enabled", False)):
        return 0
    try:
        return int(settings.get(key, default))
    except Exception:
        return default


def _xfiles_license_status_payload() -> Dict[str, Any]:
    signing_secret = _xfiles_license_signing_secret()
    local_settings = _xfiles_raw_app_settings()
    local_override_enabled = bool(
        local_settings.get("local_import_limits_enabled")
        or local_settings.get("telegram_unlimited_import_enabled")
    )
    if not signing_secret:
        invite_exists = _xfiles_invite_license_path().exists()
        state_exists = _xfiles_license_state_path().exists()
        payload = {
            "ok": False,
            "status": "verifier_missing" if invite_exists or state_exists else "missing",
            "message": (
                "XFILES_LICENSE_SIGNING_SECRET не задан: invite-license найден, но backend не может проверить подпись."
                if invite_exists or state_exists
                else "Локальная лицензия ещё не активирована."
            ),
        }
        if local_override_enabled:
            payload.update(
                {
                    "ok": True,
                    "status": "local_owner_override",
                    "message": "Локальный режим владельца продукта активен на этой машине. Клиентская лицензия не перезаписана.",
                    "plan": "local-owner",
                    "plan_title": "Local Owner Unlimited",
                    "license_kind": "local-owner",
                    "valid_until": XFILES_LOCAL_OWNER_VALID_UNTIL,
                    "days_remaining": _xfiles_local_owner_days_remaining(),
                    "features": {
                        "telegram_unlimited_import": True,
                    },
                    "limits": {
                        "import_history_months_max": 0,
                        "import_message_limit_max": 0,
                        "telegram_sources_total": None,
                    },
                }
            )
        payload["license_capabilities"] = xfiles_license_capabilities(payload.get("plan"))
        if payload.get("status") == "local_owner_override" or bool(local_settings.get("telegram_unlimited_import_enabled")):
            payload["license_capabilities"]["telegram_unlimited_import"] = True
            payload["license_capabilities"]["local_import_limit_override"] = True
            payload["license_capabilities"]["import_history_months_max"] = 0
            payload["license_capabilities"]["import_message_limit_max"] = 0
            payload["license_capabilities"]["telegram_sources_total"] = None
            if isinstance(payload["license_capabilities"].get("features"), dict):
                payload["license_capabilities"]["features"]["telegram_unlimited_import"] = True
        return _xfiles_safe_client_license_status(payload)
    payload = xfiles_license_status(state_path=_xfiles_license_state_path(), signing_secret=signing_secret)
    if payload.get("status") == "missing":
        activated = _xfiles_try_auto_activate_invite_license(signing_secret)
        if activated:
            return _xfiles_safe_client_license_status(activated)
        preview = _xfiles_invite_license_preview_payload(signing_secret)
        if preview:
            payload = preview
    if not payload.get("ok") and local_override_enabled:
        payload = {
            **payload,
            "ok": True,
            "status": "local_owner_override",
            "message": "Локальный режим владельца продукта активен на этой машине. Клиентская лицензия не перезаписана.",
            "plan": payload.get("plan") or "local-owner",
            "plan_title": payload.get("plan_title") or "Local Owner Unlimited",
            "license_kind": payload.get("license_kind") or "local-owner",
            "valid_until": payload.get("valid_until") or XFILES_LOCAL_OWNER_VALID_UNTIL,
            "days_remaining": payload.get("days_remaining") or _xfiles_local_owner_days_remaining(),
            "features": {
                **(payload.get("features") if isinstance(payload.get("features"), dict) else {}),
                "telegram_unlimited_import": True,
            },
            "limits": {
                **(payload.get("limits") if isinstance(payload.get("limits"), dict) else {}),
                "import_history_months_max": 0,
                "import_message_limit_max": 0,
                "telegram_sources_total": None,
            },
        }
    payload["license_capabilities"] = xfiles_license_capabilities(payload.get("plan"))
    if payload.get("status") == "local_owner_override" or bool(local_settings.get("telegram_unlimited_import_enabled")):
        payload["license_capabilities"]["telegram_unlimited_import"] = True
        payload["license_capabilities"]["local_import_limit_override"] = True
        payload["license_capabilities"]["import_history_months_max"] = 0
        payload["license_capabilities"]["import_message_limit_max"] = 0
        payload["license_capabilities"]["telegram_sources_total"] = None
        if isinstance(payload["license_capabilities"].get("features"), dict):
            payload["license_capabilities"]["features"]["telegram_unlimited_import"] = True
    try:
        server_url = str(os.environ.get("XFILES_LICENSE_SERVER_URL") or "").strip() or None
        payload = xfiles_refresh_license_server_status(payload, server_url=server_url)
    except Exception as exc:
        license_server = dict(payload.get("license_server") if isinstance(payload.get("license_server"), dict) else {})
        license_server.update({"online": False, "status": "refresh_failed", "error": str(exc)})
        payload["license_server"] = license_server
    return _xfiles_safe_client_license_status(payload)


def _xfiles_safe_client_license_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(payload if isinstance(payload, dict) else {})
    license_server = dict(safe.get("license_server") if isinstance(safe.get("license_server"), dict) else {})
    license_server.pop("url", None)
    safe["license_server"] = license_server
    license_id = _xfiles_read_local_license_id_for_display(safe)
    if license_id:
        safe["license_id_display"] = license_id
    invite_code = _xfiles_read_local_invite_code_for_display()
    if invite_code:
        safe["invite_code_display"] = invite_code
    for key in ("license_id", "invite_batch_id", "invite_code_masked"):
        safe.pop(key, None)
    return safe


def _xfiles_read_local_license_id_for_display(status_payload: Optional[Dict[str, Any]] = None) -> str:
    payload_candidate = ""
    if isinstance(status_payload, dict):
        payload_candidate = str(status_payload.get("license_id") or "").strip()
    if re.fullmatch(r"lic_[A-Za-z0-9_-]{8,}", payload_candidate):
        return payload_candidate
    state_path = _xfiles_license_state_path()
    if not state_path.exists():
        return ""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8", errors="replace"))
        payload = state.get("payload") if isinstance(state, dict) else {}
        candidate = str(payload.get("license_id") or "").strip() if isinstance(payload, dict) else ""
    except Exception:
        return ""
    if re.fullmatch(r"lic_[A-Za-z0-9_-]{8,}", candidate):
        return candidate
    return ""


def _xfiles_read_embedded_invite_code() -> str:
    path = _xfiles_invite_code_path()
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    fenced = re.findall(r"`([A-Za-z0-9][A-Za-z0-9_-]{4,}(?:-[A-Za-z0-9_-]{2,})*)`", text)
    for candidate in fenced:
        normalized = str(candidate or "").strip()
        if re.fullmatch(r"XF[A-Za-z0-9_-]{4,}(?:-[A-Za-z0-9_-]{2,})*", normalized, flags=re.IGNORECASE):
            return normalized
    for candidate in fenced:
        normalized = str(candidate or "").strip()
        if normalized and not normalized.lower().startswith(("lic_", "license", "activation", "invite", "http")):
            return normalized
    for line in text.splitlines():
        normalized = line.strip().strip("`")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{4,}(?:-[A-Za-z0-9_-]{2,})*", normalized):
            return normalized
    return ""


def _xfiles_read_local_invite_code_for_display() -> str:
    invite_code = _xfiles_read_embedded_invite_code()
    if invite_code:
        return invite_code
    state_path = _xfiles_license_state_path()
    if not state_path.exists():
        return ""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8", errors="replace"))
        payload = state.get("payload") if isinstance(state, dict) else {}
        candidate = str(payload.get("invite_code") or "").strip() if isinstance(payload, dict) else ""
    except Exception:
        return ""
    if re.fullmatch(r"XF[A-Za-z0-9_-]{4,}(?:-[A-Za-z0-9_-]{2,})*", candidate, flags=re.IGNORECASE):
        return candidate
    return ""


def _xfiles_try_auto_activate_invite_license(signing_secret: str) -> Dict[str, Any]:
    invite_path = _xfiles_invite_license_path()
    server_url = str(os.environ.get("XFILES_LICENSE_SERVER_URL") or "").strip()
    if not invite_path.exists() or not server_url:
        return {}
    try:
        document = json.loads(invite_path.read_text(encoding="utf-8", errors="replace"))
        license_payload = xfiles_verify_signed_document(
            document,
            signing_secret,
            expected_schema=XFILES_LICENSE_SCHEMA,
        )
    except Exception:
        return {}
    invite_code = _xfiles_read_embedded_invite_code() if bool(license_payload.get("invite_code_required", False)) else ""
    if bool(license_payload.get("invite_code_required", False)) and not invite_code:
        return {}
    try:
        instance_hash_fn = globals().get("xfiles_build_instance_hash")
        instance_hash = (
            instance_hash_fn()
            if callable(instance_hash_fn)
            else hashlib.sha256(str(socket.gethostname() or "x-files-client").encode("utf-8")).hexdigest()
        )
        xfiles_apply_license(
            document,
            state_path=_xfiles_license_state_path(),
            signing_secret=signing_secret,
            instance_hash=instance_hash,
            online_check=True,
            license_server_url=server_url,
            invite_code=invite_code,
        )
        payload = xfiles_license_status(state_path=_xfiles_license_state_path(), signing_secret=signing_secret)
        refresh_fn = globals().get("xfiles_refresh_license_server_status")
        return refresh_fn(payload, server_url=server_url) if callable(refresh_fn) else payload
    except Exception as exc:
        capabilities = xfiles_license_capabilities(license_payload.get("plan"))
        return {
            "ok": False,
            "status": "not_activated",
            "message": "Автоактивация лицензии не выполнена.",
            "read_only": True,
            "disabled_reason": f"Лицензия не активна: {exc}",
            "license_id": license_payload.get("license_id"),
            "client_email": license_payload.get("client_email"),
            "plan": license_payload.get("plan"),
            "plan_title": license_payload.get("plan_title"),
            "license_kind": license_payload.get("license_kind"),
            "valid_until": license_payload.get("valid_until"),
            "days_remaining": None,
            "license_capabilities": capabilities,
        }


def _xfiles_invite_license_preview_payload(signing_secret: str) -> Dict[str, Any]:
    invite_path = _xfiles_invite_license_path()
    if not invite_path.exists():
        return {}
    try:
        document = json.loads(invite_path.read_text(encoding="utf-8", errors="replace"))
        license_payload = xfiles_verify_signed_document(
            document,
            signing_secret,
            expected_schema=XFILES_LICENSE_SCHEMA,
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "invite_invalid",
            "message": f"Invite-license найден, но не прошёл проверку: {exc}",
            "read_only": True,
            "disabled_reason": "Invite-license повреждён или не прошёл проверку подписи.",
        }
    capabilities = xfiles_license_capabilities(license_payload.get("plan"))
    return {
        "ok": False,
        "status": "not_activated",
        "message": "Лицензия из ZIP найдена, но ещё не активирована через invite-code.",
        "read_only": True,
        "disabled_reason": "Введите invite-code при активации, чтобы включить клиентскую лицензию.",
        "license_id": license_payload.get("license_id"),
        "client_email": license_payload.get("client_email"),
        "plan": license_payload.get("plan"),
        "plan_title": license_payload.get("plan_title"),
        "release": license_payload.get("release"),
        "valid_until": license_payload.get("valid_until"),
        "days_remaining": None,
        "limits": license_payload.get("limits") if isinstance(license_payload.get("limits"), dict) else {},
        "features": license_payload.get("features") if isinstance(license_payload.get("features"), dict) else {},
        "allowed_menus": license_payload.get("allowed_menus") if isinstance(license_payload.get("allowed_menus"), list) else [],
        "disabled_menus": license_payload.get("disabled_menus") if isinstance(license_payload.get("disabled_menus"), list) else [],
        "invite_batch_id": license_payload.get("invite_batch_id"),
        "invite_code_required": bool(license_payload.get("invite_code_required", False)),
        "license_kind": license_payload.get("license_kind"),
        "activation_duration_days": license_payload.get("activation_duration_days"),
        "max_activations": license_payload.get("max_activations"),
        "license_server": {
            "url": str(license_payload.get("license_server_url") or os.environ.get("XFILES_LICENSE_SERVER_URL") or ""),
            "online": False,
            "status": "not_activated",
        },
        "license_capabilities": capabilities,
    }


def _xfiles_license_blocks_application(status: Optional[Dict[str, Any]] = None) -> bool:
    if not _xfiles_client_delivery_mode():
        return False
    status_payload = status if isinstance(status, dict) else _xfiles_license_status_payload()
    return str(status_payload.get("status") or "").strip().lower() in XFILES_LICENSE_BLOCKED_STATUSES


def _xfiles_menu_entitlements(status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    status_payload = status if isinstance(status, dict) else _xfiles_license_status_payload()
    known = [item["key"] for item in XFILES_MENU_CATALOG]
    configured_disabled = status_payload.get("disabled_menus") if isinstance(status_payload.get("disabled_menus"), list) else []
    configured_allowed = status_payload.get("allowed_menus") if isinstance(status_payload.get("allowed_menus"), list) else []
    try:
        menu_policy_version = int(status_payload.get("menu_policy_version") or 0)
    except Exception:
        menu_policy_version = 0
    computed = xfiles_compute_effective_allowed_menus(
        status_payload,
        known,
        fallback_menus=XFILES_LICENSE_FALLBACK_MENU_KEYS,
    )
    allowed = set(computed.get("effective_allowed_menus") or [])
    disabled = set(computed.get("disabled_menus") or [])
    default_disabled = set()
    if (
        str(status_payload.get("status") or "").strip().lower() == "local_owner_override"
        and not configured_allowed
    ):
        allowed = set(XFILES_LICENSE_FALLBACK_MENU_KEYS)
        disabled = set()
    elif _xfiles_license_blocks_application(status_payload):
        allowed = set(XFILES_LICENSE_RENEWAL_MENU_KEYS)
        disabled = set(known) - allowed
    elif _xfiles_client_delivery_mode():
        if menu_policy_version < 2 and not configured_disabled:
            default_disabled.update(XFILES_DEFAULT_DISABLED_MENU_KEYS)
            disabled.update(default_disabled)
        allowed.update(XFILES_CLIENT_DELIVERY_MENU_KEYS)
        allowed.difference_update(disabled)
    items = [
        {
            **item,
            "allowed": item["key"] in allowed,
            "disabled": item["key"] in disabled,
        }
        for item in XFILES_MENU_CATALOG
    ]
    return {
        "ok": bool(status_payload.get("ok")),
        "status": str(status_payload.get("status") or "missing"),
        "enforced": bool(computed.get("enforced")),
        "fallback": bool(computed.get("fallback")),
        "client_delivery": _xfiles_client_delivery_mode(),
        "effective_allowed_menus": sorted(allowed),
        "disabled_menus": sorted(disabled),
        "default_disabled_menus": sorted(default_disabled),
        "items": items,
    }


def _xfiles_menu_label(menu_key: str) -> str:
    for item in XFILES_MENU_CATALOG:
        if item.get("key") == menu_key:
            return str(item.get("label") or menu_key)
    return menu_key


def _xfiles_api_menu_key(path: str) -> Optional[str]:
    normalized_path = str(path or "")
    if not normalized_path.startswith("/api/payme/"):
        return None
    if normalized_path in XFILES_LICENSE_PUBLIC_API_PATHS:
        return None
    if any(normalized_path.startswith(prefix) for prefix in XFILES_LICENSE_PUBLIC_API_PREFIXES):
        return None
    for prefix, menu_key in XFILES_API_MENU_PREFIXES:
        if normalized_path.startswith(prefix):
            return menu_key
    return None


def _xfiles_renewal_only_response(request: Request) -> Optional[Response]:
    if not _xfiles_license_blocks_application():
        return None
    status_payload = _xfiles_license_status_payload()
    license_status = str(status_payload.get("status") or "missing")
    detail = str(
        status_payload.get("disabled_reason")
        or "Лицензия не активна или license-server недоступен. Доступ к функциям заблокирован."
    )
    path = request.url.path or "/"
    if path.startswith("/api/payme/"):
        if path in XFILES_LICENSE_PUBLIC_API_PATHS:
            return None
        if any(path.startswith(prefix) for prefix in XFILES_LICENSE_PUBLIC_API_PREFIXES):
            return None
        return JSONResponse(
            status_code=403,
            content={
                "detail": detail,
                "license_status": license_status,
                "status_url": "/settings.html#license",
            },
        )
    if path.endswith(".html") or path == "/":
        if path in XFILES_LICENSE_RENEWAL_PUBLIC_HTML:
            return None
        return RedirectResponse(url="/settings.html#license", status_code=307)
    return None


def _xfiles_audit_menu_denial(*, menu_key: str, path: str, method: str) -> None:
    try:
        status_payload = _xfiles_license_status_payload()
        _xfiles_append_license_audit(
            action="menu_denied",
            ok=False,
            status=status_payload,
            error=f"menu={menu_key} method={method} path={path}",
        )
    except Exception:
        pass


def _xfiles_api_menu_denial(request: Request) -> Optional[Response]:
    path = request.url.path or ""
    menu_key = _xfiles_api_menu_key(path)
    if not menu_key:
        return None

    try:
        entitlements = _xfiles_menu_entitlements()
    except Exception:
        return None

    allowed = set(entitlements.get("effective_allowed_menus") or [])
    if menu_key in allowed:
        return None

    _xfiles_audit_menu_denial(menu_key=menu_key, path=path, method=request.method)
    label = _xfiles_menu_label(menu_key)
    detail = (
        f"Функция '{label}' отключена текущей лицензией или недоступна без активного тарифа. "
        "Откройте страницу Тарифы или примените invite-code с доступом к этому меню."
    )
    return Response(
        content=json.dumps(
            {
                "detail": detail,
                "menu": menu_key,
                "license_status": str(entitlements.get("status") or "missing"),
            },
            ensure_ascii=False,
        ),
        status_code=403,
        media_type="application/json",
    )


def _xfiles_html_menu_denial(request: Request) -> Optional[Response]:
    path = request.url.path or ""
    if not path.endswith(".html"):
        return None
    # setup_wizard.html is a system recovery/onboarding page, not just a menu item.
    # If Telegram is not authorized and the reauthorize menu is hidden by license,
    # blocking this page creates a redirect loop:
    # import.html -> setup_wizard.html -> import.html?menu_disabled=telegram-reauthorize.
    if path == "/setup_wizard.html":
        return None
    menu_key = XFILES_HTML_MENU_PATHS.get(path)
    if not menu_key or _xfiles_is_menu_allowed(menu_key):
        return None
    _xfiles_audit_menu_denial(menu_key=menu_key, path=path, method=request.method)
    return RedirectResponse(url=f"/import.html?menu_disabled={menu_key}", status_code=307)


def _xfiles_is_menu_allowed(menu_key: str) -> bool:
    try:
        entitlements = _xfiles_menu_entitlements()
    except Exception:
        return True
    return str(menu_key or "").strip() in set(entitlements.get("effective_allowed_menus") or [])


def _xfiles_telegram_source_limit() -> Optional[int]:
    settings = _get_app_settings()
    if bool(settings.get("local_telegram_source_limit_enabled", False)):
        try:
            local_limit = int(settings.get("local_telegram_source_limit", 0) or 0)
        except (TypeError, ValueError):
            local_limit = 0
        if local_limit <= 0:
            return None
        return max(1, local_limit)
    status_payload = _xfiles_license_status_payload()
    if not status_payload.get("ok"):
        return None
    limits = status_payload.get("limits") if isinstance(status_payload.get("limits"), dict) else {}
    for key in ("telegram_sources_total", "telegram_sources", "sources_total"):
        value = limits.get(key)
        if value is None:
            continue
        try:
            limit = int(value)
        except (TypeError, ValueError):
            continue
        if limit >= 0:
            return limit
    return None


def _xfiles_license_limit_int(keys: Iterable[str], default: int, *, min_value: int = 1) -> int:
    status_payload = _xfiles_license_status_payload()
    limits = status_payload.get("limits") if isinstance(status_payload.get("limits"), dict) else {}
    for key in keys:
        value = limits.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= min_value:
            return parsed
    return max(min_value, int(default))


def _local_import_limit_override() -> Dict[str, int]:
    raw: Dict[str, Any] = {}
    sync = globals().get("telegram_sync")
    if sync is not None and isinstance(getattr(sync, "state", None), dict):
        maybe = sync.state.get(APP_SETTINGS_STATE_KEY)
        if isinstance(maybe, dict):
            raw = maybe
    if not raw and STATE_PATH.exists():
        try:
            state_payload = json.loads(STATE_PATH.read_text(encoding="utf-8", errors="replace"))
            maybe = state_payload.get(APP_SETTINGS_STATE_KEY) if isinstance(state_payload, dict) else None
            if isinstance(maybe, dict):
                raw = maybe
        except Exception:
            raw = {}
    if bool(raw.get("telegram_unlimited_import_enabled", False)):
        return {
            "import_history_months_max": 0,
            "import_message_limit_max": 0,
        }
    if not bool(raw.get("local_import_limits_enabled", False)):
        return {}

    def _positive_int(key: str, default: int, max_value: int) -> int:
        try:
            value = int(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(1, min(max_value, value))

    return {
        "import_history_months_max": _positive_int("local_import_max_history_months", 1, 1200),
        "import_message_limit_max": _positive_int("local_import_max_message_limit", 1000, 100000000),
    }


def _xfiles_import_history_months_max() -> int:
    licensed = _xfiles_license_limit_int(
        ("import_history_months_max", "telegram_history_months_max", "history_months_max"),
        1,
        min_value=0,
    )
    override = _local_import_limit_override().get("import_history_months_max")
    if override == 0 or licensed == 0:
        return 0
    return max(licensed, int(override or 0))


def _xfiles_import_message_limit_max() -> int:
    licensed = _xfiles_license_limit_int(
        ("import_message_limit_max", "telegram_message_limit_max", "messages_per_source_max"),
        1000,
        min_value=0,
    )
    override = _local_import_limit_override().get("import_message_limit_max")
    if override == 0 or licensed == 0:
        return 0
    return max(licensed, int(override or 0))


def _xfiles_current_telegram_source_count(selectors: Optional[List[str]] = None) -> int:
    source_selectors = selectors if selectors is not None else _source_selectors_as_strings()
    identities = {
        _selector_identity(item)
        for item in source_selectors
        if _selector_identity(item)
    }
    return len(identities)


def _xfiles_tariff_source_usage_payload(
    *,
    status_payload: Optional[Dict[str, Any]] = None,
    selectors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    status = status_payload if isinstance(status_payload, dict) else _xfiles_license_status_payload()
    plan_key = str(status.get("plan") or "free-demo").strip() or "free-demo"
    plan = xfiles_tariff_plan(plan_key)
    limit = _xfiles_telegram_source_limit() if status_payload is None else None
    if status_payload is not None:
        limits = status.get("limits") if isinstance(status.get("limits"), dict) else {}
        for key in ("telegram_sources_total", "telegram_sources", "sources_total"):
            value = limits.get(key)
            if value is None:
                continue
            try:
                limit = max(0, int(value))
                break
            except (TypeError, ValueError):
                continue
    used = _xfiles_current_telegram_source_count(selectors)
    ratio = None if limit in (None, 0) else min(1.0, used / max(1, int(limit)))
    severity = "ok"
    messages: List[str] = []
    if limit is not None:
        if used >= limit:
            severity = "blocked"
            messages.append(
                f"Лимит Telegram-источников исчерпан: {used} из {limit}. "
                "Удалите источник из сканирования или обновите тариф."
            )
        elif ratio is not None and ratio >= 0.8:
            severity = "warning"
            messages.append(
                f"Использовано {used} из {limit} Telegram-источников. "
                "Скоро понадобится апгрейд тарифа."
            )
    return {
        "used": used,
        "limit": limit,
        "remaining": None if limit is None else max(0, int(limit) - used),
        "ratio": ratio,
        "percent": None if ratio is None else round(ratio * 100, 1),
        "severity": severity,
        "messages": messages,
        "upgrade_hint": str(plan.get("upgrade_hint") or ""),
        "plan": plan_key,
    }


def _xfiles_append_license_audit(
    *,
    action: str,
    ok: bool,
    document: Optional[Dict[str, Any]] = None,
    status: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> None:
    try:
        record = xfiles_build_license_audit_record(
            action=action,
            ok=ok,
            document=document,
            status=status,
            error=error,
        )
        xfiles_append_license_audit_record(_xfiles_license_audit_path(), record)
    except Exception as exc:
        logging.warning("x-files license audit write failed: %s", exc)


def _xfiles_license_email_runtime_settings() -> Dict[str, Any]:
    settings = _get_app_settings()
    if not settings.get("license_email_enabled"):
        raise HTTPException(status_code=400, detail="Email-импорт лицензий выключен в настройках")
    host = str(settings.get("license_email_host") or "").strip()
    login = str(settings.get("license_email_login") or "").strip()
    password = _decrypt_client_email_password(settings.get("license_email_password_secret"))
    if not host or not login or not password:
        raise HTTPException(status_code=422, detail="Укажите IMAP host, email/login и app-password для импорта лицензий")
    return {
        **settings,
        "license_email_host": host,
        "license_email_login": login,
        "license_email_password": password,
    }


def _xfiles_try_parse_invite_license_json(raw: bytes) -> Optional[Dict[str, Any]]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(document, dict):
        return None
    payload = document.get("payload")
    if isinstance(payload, dict) and payload.get("schema") == XFILES_LICENSE_SCHEMA and document.get("signature"):
        return document
    return None


def _xfiles_extract_invite_license_from_email(raw_message: bytes) -> Optional[Dict[str, Any]]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    parts = list(message.walk()) if message.is_multipart() else [message]

    for part in parts:
        filename = str(part.get_filename() or "").lower()
        content_type = str(part.get_content_type() or "").lower()
        if "invite-license" not in filename and not filename.endswith(".json") and content_type != "application/json":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        document = _xfiles_try_parse_invite_license_json(payload)
        if document:
            return document

    for part in parts:
        content_type = str(part.get_content_type() or "").lower()
        if not content_type.startswith("text/"):
            continue
        try:
            content = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            try:
                content = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                content = ""
        if not content:
            continue
        start = content.find('{"payload"')
        if start < 0:
            start = content.find("{\n  \"payload\"")
        if start < 0:
            continue
        document = _xfiles_try_parse_invite_license_json(content[start:].strip().encode("utf-8"))
        if document:
            return document
    return None


def _xfiles_fetch_invite_license_from_email_sync(
    *,
    limit: int = 20,
    imap_factory: Any = imaplib.IMAP4_SSL,
) -> tuple[Dict[str, Any], str]:
    settings = _xfiles_license_email_runtime_settings()
    mailbox = str(settings.get("license_email_inbox_folder") or "INBOX").strip() or "INBOX"
    host = str(settings["license_email_host"])
    port = int(settings.get("license_email_port") or 993)
    login = str(settings["license_email_login"])
    password = str(settings["license_email_password"])
    client = imap_factory(host, port)
    try:
        client.login(login, password)
        status, _ = client.select(mailbox)
        if str(status).upper() != "OK":
            raise HTTPException(status_code=502, detail=f"Не удалось открыть папку почты: {mailbox}")
        status, data = client.search(None, "ALL")
        if str(status).upper() != "OK":
            raise HTTPException(status_code=502, detail="Не удалось прочитать список писем с invite-license")
        message_ids = list((data[0] or b"").split())[-max(1, min(int(limit or 20), 100)) :]
        for message_id in reversed(message_ids):
            fetch_status, fetch_data = client.fetch(message_id, "(RFC822)")
            if str(fetch_status).upper() != "OK":
                continue
            for item in fetch_data or []:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                raw_message = item[1]
                if not isinstance(raw_message, (bytes, bytearray)):
                    continue
                document = _xfiles_extract_invite_license_from_email(bytes(raw_message))
                if document:
                    return document, message_id.decode("ascii", errors="ignore")
    finally:
        try:
            client.logout()
        except Exception:
            pass
    raise HTTPException(status_code=404, detail="В последних письмах invite-license.json не найден")


def _xfiles_receipt_target_email(document: Optional[Dict[str, Any]]) -> str:
    payload = document.get("payload") if isinstance(document, dict) else {}
    if isinstance(payload, dict):
        root_email = str(payload.get("root_email") or "").strip()
        if root_email:
            return root_email
    return "aidialog@mail.ru"


def _xfiles_send_activation_receipt_email_sync(
    *,
    target_email: str,
    smtp_factory: Any = smtplib.SMTP_SSL,
) -> bool:
    settings = _get_app_settings()
    if not settings.get("license_email_allow_activation_receipt"):
        return False
    login = str(settings.get("license_email_login") or "").strip()
    password = _decrypt_client_email_password(settings.get("license_email_password_secret"))
    if not login or not password or not target_email:
        return False
    smtp_host = str(settings.get("license_email_smtp_host") or "").strip()
    if not smtp_host:
        imap_host = str(settings.get("license_email_host") or "").strip()
        smtp_host = re.sub(r"^imap([.-])", r"smtp\1", imap_host) if imap_host else ""
    if not smtp_host:
        return False
    smtp_port = int(settings.get("license_email_smtp_port") or 465)
    signing_secret = _xfiles_license_signing_secret()
    if not signing_secret:
        return False
    receipt = xfiles_build_activation_receipt(
        state_path=_xfiles_license_state_path(),
        signing_secret=signing_secret,
        app_version=str(os.environ.get("XFILES_RELEASE_VERSION") or ""),
    )
    body = json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8")
    message = EmailMessage()
    message["From"] = login
    message["To"] = target_email
    message["Subject"] = "x-files activation receipt"
    message.set_content(
        "Квитанция активации x-files во вложении. "
        "В письме нет сообщений Telegram, CRM-строк, сделок, OCR-текста или пользовательских данных."
    )
    message.add_attachment(body, maintype="application", subtype="json", filename="activation-receipt.json")
    client = smtp_factory(smtp_host, smtp_port, context=ssl.create_default_context())
    try:
        client.login(login, password)
        client.send_message(message)
        return True
    finally:
        try:
            client.quit()
        except Exception:
            pass


def _xfiles_read_invite_document(payload: Optional["XFilesLicenseActivatePayload"] = None) -> Dict[str, Any]:
    if payload and isinstance(payload.invite_license, dict) and payload.invite_license:
        return payload.invite_license
    if payload and payload.invite_license_json.strip():
        try:
            document = json.loads(payload.invite_license_json)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invite_license_json не является JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise HTTPException(status_code=422, detail="invite_license_json должен быть JSON object")
        return document
    invite_path = _xfiles_invite_license_path()
    if not invite_path.exists():
        raise HTTPException(status_code=404, detail=f"invite-license не найден: {invite_path}")
    try:
        document = json.loads(invite_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invite-license повреждён: {exc}") from exc
    if not isinstance(document, dict):
        raise HTTPException(status_code=422, detail="invite-license должен быть JSON object")
    return document


def _xfiles_apply_invite_license(
    payload: Optional["XFilesLicenseActivatePayload"],
    *,
    action: str,
    allowed_kinds: set[str],
    success_message: str,
) -> "XFilesLicenseActionDTO":
    signing_secret = _xfiles_license_signing_secret()
    if not signing_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "XFILES_LICENSE_SIGNING_SECRET не задан. "
                "Backend не будет применять invite-code без проверки подписи."
            ),
        )

    document: Optional[Dict[str, Any]] = None
    try:
        document = _xfiles_read_invite_document(payload)
        license_payload = xfiles_verify_signed_document(
            document,
            signing_secret,
            expected_schema=XFILES_LICENSE_SCHEMA,
        )
        license_kind = str(license_payload.get("license_kind") or "activation").strip()
        if license_kind not in allowed_kinds:
            allowed = ", ".join(sorted(allowed_kinds))
            message = f"Этот endpoint принимает license_kind: {allowed}; получено: {license_kind or 'empty'}"
            _xfiles_append_license_audit(action=action, ok=False, document=document, error=message)
            raise HTTPException(status_code=422, detail=message)

        xfiles_apply_license(
            document,
            state_path=_xfiles_license_state_path(),
            signing_secret=signing_secret,
            instance_hash=xfiles_build_instance_hash(),
            online_check=True,
            license_server_url=str(os.environ.get("XFILES_LICENSE_SERVER_URL") or "").strip() or None,
            invite_code=str(getattr(payload, "invite_code", "") or "").strip() if payload else "",
        )
    except HTTPException:
        raise
    except XFilesLicenseError as exc:
        _xfiles_append_license_audit(action=action, ok=False, document=document, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    status_payload = _xfiles_license_status_payload()
    _xfiles_append_license_audit(action=action, ok=True, document=document, status=status_payload)
    status = XFilesLicenseStatusDTO(**status_payload)
    return XFilesLicenseActionDTO(ok=True, message=success_message, status=status)


def _resolve_telegram_api_credentials(settings: Optional[Dict[str, Any]] = None) -> tuple[Optional[int], str]:
    normalized = _coerce_app_settings(settings if settings is not None else _get_app_settings())
    api_id_raw = _normalize_telegram_api_id(normalized.get("telegram_api_id"))
    api_hash = _normalize_telegram_api_hash(normalized.get("telegram_api_hash"))
    if not api_id_raw or not api_hash:
        return None, ""
    return int(api_id_raw), api_hash


def _require_telegram_api_credentials() -> tuple[int, str]:
    api_id, api_hash = _resolve_telegram_api_credentials()
    if not api_id or not api_hash:
        raise HTTPException(
            status_code=400,
            detail="Укажите Telegram api_id и api_hash в настройках или стартовой форме авторизации",
        )
    return api_id, api_hash


for _name, _value in list(globals().items()):
    if _name.startswith("_") and callable(_value) and _name not in {"_with_legacy_globals"}:
        globals()[_name] = _with_legacy_globals(_value)

__all__ = (
    "annotations",
    "base64",
    "hashlib",
    "hmac",
    "imaplib",
    "json",
    "logging",
    "os",
    "re",
    "smtplib",
    "socket",
    "ssl",
    "sys",
    "policy",
    "EmailMessage",
    "BytesParser",
    "wraps",
    "Path",
    "Any",
    "Dict",
    "Iterable",
    "List",
    "Optional",
    "Union",
    "HTTPException",
    "Request",
    "JSONResponse",
    "RedirectResponse",
    "Response",
    "_with_legacy_globals",
    "CLIENT_EMAIL_SECRET_SCHEMA",
    "_client_email_secret_key",
    "_client_email_secret_stream",
    "_encrypt_client_email_password",
    "_decrypt_client_email_password",
    "_client_email_password_configured",
    "_openrouter_timeout_sec",
    "_xfiles_license_dir",
    "_xfiles_license_state_path",
    "_xfiles_invite_license_path",
    "_xfiles_invite_code_path",
    "_xfiles_license_audit_path",
    "_xfiles_release_manifest_path",
    "_xfiles_client_delivery_mode",
    "_xfiles_license_signing_secret",
    "_xfiles_manifest_signing_secret",
    "_xfiles_compact_json_bytes",
    "_xfiles_verify_root_signature",
    "_xfiles_update_status_payload",
    "_xfiles_license_status_payload",
    "_xfiles_safe_client_license_status",
    "_xfiles_read_embedded_invite_code",
    "_xfiles_try_auto_activate_invite_license",
    "_xfiles_license_blocks_application",
    "_xfiles_menu_entitlements",
    "_xfiles_menu_label",
    "_xfiles_api_menu_key",
    "_xfiles_renewal_only_response",
    "_xfiles_audit_menu_denial",
    "_xfiles_api_menu_denial",
    "_xfiles_html_menu_denial",
    "_xfiles_is_menu_allowed",
    "_xfiles_telegram_source_limit",
    "_xfiles_license_limit_int",
    "_local_import_limit_override",
    "_xfiles_import_history_months_max",
    "_xfiles_import_message_limit_max",
    "_xfiles_current_telegram_source_count",
    "_xfiles_tariff_source_usage_payload",
    "_xfiles_append_license_audit",
    "_xfiles_license_email_runtime_settings",
    "_xfiles_try_parse_invite_license_json",
    "_xfiles_extract_invite_license_from_email",
    "_xfiles_fetch_invite_license_from_email_sync",
    "_xfiles_receipt_target_email",
    "_xfiles_send_activation_receipt_email_sync",
    "_xfiles_read_invite_document",
    "_xfiles_apply_invite_license",
    "_resolve_telegram_api_credentials",
    "_require_telegram_api_credentials",
)
