"""Bitrix24 export provider for GramLead CRM data.

The module is intentionally self-contained: it stores only Bitrix24 export
state and never writes to the GramLead DuckDB writer database.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.runtime_paths import CACHE_DIR

AuthMode = Literal["webhook", "oauth"]
JobStatus = Literal["created", "running", "done", "cancelled", "error"]

STATE_PATH = CACHE_DIR / "crm_exports" / "bitrix24.json"
YAML_CONFIG_PATH = Path(os.getenv("CRM_EXPORT_CONFIG_PATH") or "/app/config/crm_exports.local.yaml")
DUCKDB_READ_PATH = Path(os.getenv("PAYME_DUCKDB_READ_PATH") or "/data/db/duckdb/gramlead-read.duckdb")
APP_SETTINGS_PATH = Path(os.getenv("CRM_EXPORT_APP_SETTINGS_PATH") or "/data/state/state.json")
ARTIFACTS_DIR = Path(os.getenv("CRM_EXPORT_ARTIFACTS_DIR") or "/data/out/crm_exports/bitrix24/contact_messages")
PUBLIC_BASE_URL = str(os.getenv("CRM_EXPORT_PUBLIC_BASE_URL") or "http://127.0.0.1:8024").strip().rstrip("/")
OPENROUTER_CHAT_URL = str(
    os.getenv("CRM_EXPORT_OPENROUTER_CHAT_URL") or "https://openrouter.ai/api/v1/chat/completions"
).strip()
DEFAULT_OPENROUTER_MODEL_ID = "openai/gpt-oss-120b:free"
DEFAULT_OPENROUTER_PROMPT = (
    "Оцени, может ли этот человек купить GramLead. Дай короткий вывод: вероятность покупки, "
    "почему, что написать первым сообщением, какие риски. Не выдумывай факты."
)

GRAMLEAD_CUSTOM_FIELDS = [
    {"name": "UF_CRM_GRAMLEAD_EXTERNAL_ID", "title": "GramLead External ID", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_SOURCE", "title": "GramLead Source", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_SOURCE_TITLE", "title": "GramLead Source Title", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_TG_USERNAME", "title": "Telegram Username", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_TG_ID", "title": "Telegram ID", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_MESSAGE_ID", "title": "GramLead Message ID", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_SCORE", "title": "GramLead Score", "type": "double"},
    {"name": "UF_CRM_GRAMLEAD_LAST_MESSAGE_AT", "title": "Last Message At", "type": "datetime"},
    {"name": "UF_CRM_GRAMLEAD_EXPORT_BATCH", "title": "GramLead Export Batch", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_CONTACT_MESSAGES_COUNT", "title": "GramLead Messages Count", "type": "double"},
    {"name": "UF_CRM_GRAMLEAD_CONTACT_JSONL_URL", "title": "GramLead JSONL URL", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_CONTACT_HTML_URL", "title": "GramLead HTML URL", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_CONTACT_XLSX_URL", "title": "GramLead XLSX URL", "type": "string"},
    {"name": "UF_CRM_GRAMLEAD_CONTACT_DOCX_URL", "title": "GramLead OpenRouter DOCX URL", "type": "string"},
]


class Bitrix24ConnectionPayload(BaseModel):
    portal_url: str = ""
    auth_mode: AuthMode = "webhook"
    webhook_url: str = ""
    access_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    selected_entity: Literal["lead", "deal"] = "lead"
    dry_run_limit: int = Field(default=25, ge=1, le=50000)
    duckdb_read_path: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL_ID
    openrouter_prompt: str = DEFAULT_OPENROUTER_PROMPT
    openrouter_contact_limit: int = Field(default=10, ge=1, le=50000)
    openrouter_timeout_sec: float = Field(default=120.0, ge=5.0, le=300.0)


class Bitrix24RunPayload(BaseModel):
    dry_run: bool = False
    limit: int = Field(default=100, ge=1, le=50000)
    export_contacts: bool = True
    export_leads: bool = True
    export_timeline: bool = True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> Dict[str, Any]:
    return {
        "settings": {
            "portal_url": "",
            "auth_mode": "webhook",
            "webhook_url": "",
            "access_token": "",
            "client_id": "",
            "client_secret": "",
            "refresh_token": "",
            "selected_entity": "lead",
            "dry_run_limit": 25,
            "duckdb_read_path": str(DUCKDB_READ_PATH),
            "openrouter_api_key": "",
            "openrouter_model": DEFAULT_OPENROUTER_MODEL_ID,
            "openrouter_prompt": DEFAULT_OPENROUTER_PROMPT,
            "openrouter_contact_limit": 10,
            "openrouter_timeout_sec": 120.0,
        },
        "capabilities": {},
        "custom_fields": [],
        "jobs": {},
        "mappings": [],
        "connection_checks": [],
        "updated_at": None,
    }


def _parse_simple_yaml_scalar(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return ""
    if text[0:1] in {"'", '"'} and text[-1:] == text[0]:
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(text)
    except ValueError:
        return text


def _load_simple_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    result: Dict[str, Any] = {}
    current_section = ""
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not raw_line.startswith((" ", "\t")) and stripped.endswith(":"):
                current_section = stripped[:-1].strip()
                result.setdefault(current_section, {})
                continue
            if ":" not in stripped or not current_section:
                continue
            key, value = stripped.split(":", 1)
            section = result.setdefault(current_section, {})
            if isinstance(section, dict):
                section[key.strip()] = _parse_simple_yaml_scalar(value)
    except Exception:
        return {}
    return result


def _yaml_bitrix_settings() -> Dict[str, Any]:
    config = _load_simple_yaml(YAML_CONFIG_PATH)
    section = config.get("bitrix24") if isinstance(config, dict) else {}
    if not isinstance(section, dict):
        return {}
    allowed = set(_default_state()["settings"].keys())
    return {key: value for key, value in section.items() if key in allowed and value not in (None, "")}


def _apply_yaml_settings(state: Dict[str, Any]) -> Dict[str, Any]:
    settings = _yaml_bitrix_settings()
    if not settings:
        return state
    current = dict(state.get("settings") or {})
    current.update(settings)
    current["portal_url"] = str(current.get("portal_url") or "").strip().rstrip("/")
    current["webhook_url"] = str(current.get("webhook_url") or "").strip().rstrip("/")
    current["auth_mode"] = "oauth" if current.get("auth_mode") == "oauth" else "webhook"
    current["selected_entity"] = "deal" if current.get("selected_entity") == "deal" else "lead"
    current["dry_run_limit"] = max(1, min(50000, int(current.get("dry_run_limit") or 25)))
    state["settings"] = current
    state["yaml_config"] = {
        "path": str(YAML_CONFIG_PATH),
        "loaded": True,
        "keys": sorted(settings.keys()),
    }
    return state


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return _apply_yaml_settings(_default_state())
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state = _default_state()
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in state:
                    state[key] = value
        if not isinstance(state.get("settings"), dict):
            state["settings"] = _default_state()["settings"]
        else:
            merged_settings = dict(_default_state()["settings"])
            merged_settings.update(state.get("settings") or {})
            state["settings"] = merged_settings
        return _apply_yaml_settings(state)
    except Exception:
        return _apply_yaml_settings(_default_state())


def _save_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state["updated_at"] = utc_now()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_PATH)
    return state


def _mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 10:
        return f"{text[:2]}…{text[-2:]}"
    return f"{text[:6]}…{text[-4:]}"


def _safe_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(settings or {})
    safe["webhook_configured"] = bool(str(safe.get("webhook_url") or "").strip())
    safe["access_token_configured"] = bool(str(safe.get("access_token") or "").strip())
    safe["client_secret_configured"] = bool(str(safe.get("client_secret") or "").strip())
    safe["refresh_token_configured"] = bool(str(safe.get("refresh_token") or "").strip())
    safe["openrouter_api_key_configured"] = bool(str(safe.get("openrouter_api_key") or "").strip())
    safe["webhook_url_masked"] = _mask_secret(str(safe.get("webhook_url") or ""))
    safe["access_token_masked"] = _mask_secret(str(safe.get("access_token") or ""))
    safe["client_secret_masked"] = _mask_secret(str(safe.get("client_secret") or ""))
    safe["refresh_token_masked"] = _mask_secret(str(safe.get("refresh_token") or ""))
    safe["openrouter_api_key_masked"] = _mask_secret(str(safe.get("openrouter_api_key") or ""))
    for key in ("webhook_url", "access_token", "client_secret", "refresh_token", "openrouter_api_key"):
        safe.pop(key, None)
    return safe


def get_settings() -> Dict[str, Any]:
    state = _load_state()
    return {
        "ok": True,
        "settings": _safe_settings(state.get("settings", {})),
        "capabilities": state.get("capabilities") or {},
        "custom_fields": state.get("custom_fields") or [],
        "updated_at": state.get("updated_at"),
    }


def save_settings(payload: Bitrix24ConnectionPayload) -> Dict[str, Any]:
    state = _load_state()
    current = dict(state.get("settings") or {})
    incoming = payload.model_dump()
    for key, value in incoming.items():
        if key in {"webhook_url", "access_token", "client_secret", "refresh_token", "openrouter_api_key"} and not str(value or "").strip():
            continue
        current[key] = str(value).strip() if isinstance(value, str) else value
    current["portal_url"] = str(current.get("portal_url") or "").strip().rstrip("/")
    current["auth_mode"] = "oauth" if current.get("auth_mode") == "oauth" else "webhook"
    current["selected_entity"] = "deal" if current.get("selected_entity") == "deal" else "lead"
    current["dry_run_limit"] = max(1, min(500, int(current.get("dry_run_limit") or 25)))
    current["duckdb_read_path"] = str(current.get("duckdb_read_path") or str(DUCKDB_READ_PATH)).strip()
    current["openrouter_model"] = str(current.get("openrouter_model") or DEFAULT_OPENROUTER_MODEL_ID).strip()
    current["openrouter_prompt"] = str(current.get("openrouter_prompt") or DEFAULT_OPENROUTER_PROMPT).strip()
    current["openrouter_contact_limit"] = max(1, min(50000, int(current.get("openrouter_contact_limit") or 10)))
    current["openrouter_timeout_sec"] = max(5.0, min(300.0, float(current.get("openrouter_timeout_sec") or 120.0)))
    state["settings"] = current
    _save_state(state)
    return {
        "ok": True,
        "message": "Настройки Bitrix24 сохранены. Секреты замаскированы и не возвращаются во frontend.",
        "settings": _safe_settings(current),
    }


class Bitrix24Error(RuntimeError):
    def __init__(self, message: str, *, code: str = "", status: int = 0, raw: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.raw = raw


class Bitrix24Client:
    def __init__(self, settings: Dict[str, Any], *, timeout_sec: float = 20.0) -> None:
        self.settings = settings
        self.timeout_sec = timeout_sec

    def _method_url(self, method: str) -> str:
        auth_mode = self.settings.get("auth_mode") or "webhook"
        if auth_mode == "webhook":
            base = str(self.settings.get("webhook_url") or "").strip().rstrip("/")
            if not base:
                raise Bitrix24Error("Bitrix24 webhook URL не задан", code="missing_webhook")
            return f"{base}/{method}.json"
        portal = str(self.settings.get("portal_url") or "").strip().rstrip("/")
        if not portal:
            raise Bitrix24Error("Bitrix24 portal URL не задан", code="missing_portal_url")
        return f"{portal}/rest/{method}.json"

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = dict(params or {})
        if self.settings.get("auth_mode") == "oauth":
            token = str(self.settings.get("access_token") or "").strip()
            if not token:
                raise Bitrix24Error("Bitrix24 OAuth access token не задан", code="missing_access_token")
            payload["auth"] = token
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._method_url(method),
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise Bitrix24Error(
                _normalize_error_message(raw) or f"Bitrix24 HTTP {exc.code}",
                code="http_error",
                status=exc.code,
                raw=raw,
            ) from exc
        except Exception as exc:
            raise Bitrix24Error(f"Bitrix24 network error: {exc}", code="network_error") from exc
        try:
            parsed = json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise Bitrix24Error("Bitrix24 вернул не JSON ответ", code="invalid_json", raw=body) from exc
        if isinstance(parsed, dict) and parsed.get("error"):
            raise Bitrix24Error(
                str(parsed.get("error_description") or parsed.get("error") or "Bitrix24 error"),
                code=str(parsed.get("error") or "bitrix_error"),
                raw=parsed,
            )
        return parsed if isinstance(parsed, dict) else {"result": parsed}


def _normalize_error_message(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("error_description") or raw.get("error") or "").strip()
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return _normalize_error_message(parsed)
    except Exception:
        pass
    return text[:500]


def _build_capabilities(settings: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "auth_mode": settings.get("auth_mode") or "webhook",
        "crm_scope_required": True,
        "universal_api_preferred": True,
        "legacy_methods_fallback": True,
        "batch_supported": True,
        "timeline_comments_supported": True,
        "custom_fields_setup_supported": True,
        "last_profile_result": result.get("result") if isinstance(result, dict) else None,
        "checked_at": utc_now(),
    }


def test_connection() -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    check = {
        "ts": utc_now(),
        "portal_url": settings.get("portal_url") or "",
        "auth_mode": settings.get("auth_mode") or "webhook",
        "ok": False,
        "error": "",
    }
    try:
        client = Bitrix24Client(settings)
        profile = client.call("profile")
        capabilities = _build_capabilities(settings, profile)
        state["capabilities"] = capabilities
        check["ok"] = True
        check["result"] = "profile ok"
        message = "Подключение Bitrix24 проверено: profile доступен."
    except Bitrix24Error as exc:
        check["error"] = f"{exc.code}: {exc}"
        capabilities = _build_capabilities(settings)
        state["capabilities"] = capabilities
        message = f"Bitrix24 не проверен: {exc}"
    checks = list(state.get("connection_checks") or [])
    checks.insert(0, check)
    state["connection_checks"] = checks[:20]
    _save_state(state)
    return {
        "ok": bool(check.get("ok")),
        "message": message,
        "settings": _safe_settings(settings),
        "capabilities": capabilities,
        "check": check,
    }


def _bitrix_userfield_payload(field: Dict[str, Any]) -> Dict[str, Any]:
    title = str(field.get("title") or field.get("name") or "")
    user_type = str(field.get("type") or "string")
    if user_type == "datetime":
        user_type = "datetime"
    elif user_type == "double":
        user_type = "double"
    else:
        user_type = "string"
    return {
        "FIELD_NAME": str(field.get("name") or ""),
        "USER_TYPE_ID": user_type,
        "XML_ID": str(field.get("name") or ""),
        "EDIT_FORM_LABEL": title,
        "LIST_COLUMN_LABEL": title,
        "LIST_FILTER_LABEL": title,
    }


def setup_custom_fields(dry_run: bool = False) -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    target_methods = {
        "contact": ("crm.contact.userfield.list", "crm.contact.userfield.add"),
        "lead": ("crm.lead.userfield.list", "crm.lead.userfield.add"),
    }
    if settings.get("selected_entity") == "deal":
        target_methods["deal"] = ("crm.deal.userfield.list", "crm.deal.userfield.add")

    fields = []
    errors = []
    client = None if dry_run else Bitrix24Client(settings)
    for entity, (list_method, add_method) in target_methods.items():
        existing_names = set()
        if client is not None:
            try:
                listed = client.call(list_method, {})
                result = listed.get("result") or []
                if isinstance(result, list):
                    existing_names = {str(item.get("FIELD_NAME") or item.get("fieldName") or "") for item in result if isinstance(item, dict)}
            except Bitrix24Error as exc:
                errors.append({"entity": entity, "method": list_method, "error": str(exc), "code": exc.code})
        for item in GRAMLEAD_CUSTOM_FIELDS:
            name = str(item.get("name") or "")
            status = "planned" if dry_run else "exists" if name in existing_names else "created"
            record = dict(item, entity=entity, status=status)
            if client is not None and name not in existing_names:
                try:
                    response = client.call(add_method, {"fields": _bitrix_userfield_payload(item)})
                    record["bitrix_result"] = response.get("result")
                except Bitrix24Error as exc:
                    record["status"] = "error"
                    record["error"] = str(exc)
                    errors.append({"entity": entity, "field": name, "method": add_method, "error": str(exc), "code": exc.code})
            fields.append(record)
    if not dry_run:
        state["custom_fields"] = fields
        state["custom_fields_errors"] = errors[-100:]
        _save_state(state)
    return {
        "ok": not errors,
        "dry_run": bool(dry_run),
        "message": (
            "Поля GramLead для Bitrix24 подготовлены."
            if not errors and not dry_run
            else "Dry-run: поля Bitrix24 будут подготовлены."
            if dry_run
            else "Поля Bitrix24 подготовлены частично: есть ошибки, проверьте права CRM."
        ),
        "settings": _safe_settings(settings),
        "custom_fields": fields,
        "errors": errors,
    }


def _stable_external_id(row: Dict[str, Any], *, prefix: str = "contact") -> str:
    for key in ("contact_key", "id", "message_id", "sender_id"):
        value = row.get(key)
        if value not in (None, ""):
            return f"gramlead:{prefix}:{value}"
    digest = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"gramlead:{prefix}:{digest[:24]}"


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 20)].rstrip()}\n...обрезано..."


def _contact_visible_comment(row: Dict[str, Any]) -> str:
    links = [
        ("JSONL", row.get("artifact_jsonl_url")),
        ("HTML", row.get("artifact_html_url")),
        ("Excel", row.get("artifact_xlsx_url")),
        ("DOCX OpenRouter", row.get("artifact_docx_url")),
    ]
    lines = [
        "GramLead",
        f"Источник: {row.get('source_title') or row.get('source') or row.get('latest_lead') or '-'}",
        f"Контакт: {row.get('fio') or row.get('name') or row.get('sender_name') or '-'}",
        f"Telegram: @{row.get('username') or row.get('sender_username') or '-'} / ID {row.get('sender_id') or row.get('telegram_id') or '-'}",
        f"Сообщений в базе: {int(row.get('messages_count') or 0)}",
        f"Последнее сообщение: {row.get('last_message_at') or '-'}",
    ]
    latest_text = str(row.get("latest_message_text") or "").strip()
    if latest_text:
        lines.append(f"Последний текст: {_truncate_text(latest_text, 700)}")
    openrouter_answer = str(row.get("openrouter_answer") or "").strip()
    if openrouter_answer:
        lines.extend(["", "OpenRouter:", _truncate_text(openrouter_answer, 3500)])
    lines.append("")
    lines.append("Файлы контакта:")
    for label, url in links:
        if url:
            lines.append(f"{label}: {url}")
    return _truncate_text("\n".join(lines), 12000)


def _contact_timeline_comment(row: Dict[str, Any]) -> str:
    return _truncate_text(_contact_visible_comment(row), 9000)


def _contact_payload(row: Dict[str, Any], *, batch_id: str) -> Dict[str, Any]:
    name = str(row.get("fio") or row.get("name") or row.get("sender_name") or row.get("contact_key") or "GramLead contact")
    phones = row.get("phones") if isinstance(row.get("phones"), list) else []
    emails = row.get("emails") if isinstance(row.get("emails"), list) else []
    source = str(row.get("latest_lead") or row.get("lead") or row.get("source") or "")
    username = str(row.get("username") or row.get("sender_username") or "")
    fields: Dict[str, Any] = {
        "NAME": name[:250],
        "COMMENTS": _contact_visible_comment(row),
        "SOURCE_ID": "OTHER",
        "SOURCE_DESCRIPTION": source,
        "OPENED": "Y",
        "TYPE_ID": "CLIENT",
        "POST": "GramLead Telegram contact",
        "UF_CRM_GRAMLEAD_EXTERNAL_ID": _stable_external_id(row),
        "UF_CRM_GRAMLEAD_SOURCE": source,
        "UF_CRM_GRAMLEAD_SOURCE_TITLE": str(row.get("source_title") or source),
        "UF_CRM_GRAMLEAD_TG_USERNAME": username,
        "UF_CRM_GRAMLEAD_TG_ID": str(row.get("sender_id") or row.get("telegram_id") or ""),
        "UF_CRM_GRAMLEAD_LAST_MESSAGE_AT": str(row.get("last_message_at") or ""),
        "UF_CRM_GRAMLEAD_EXPORT_BATCH": batch_id,
        "UF_CRM_GRAMLEAD_CONTACT_MESSAGES_COUNT": int(row.get("messages_count") or 0),
        "UF_CRM_GRAMLEAD_CONTACT_JSONL_URL": str(row.get("artifact_jsonl_url") or ""),
        "UF_CRM_GRAMLEAD_CONTACT_HTML_URL": str(row.get("artifact_html_url") or ""),
        "UF_CRM_GRAMLEAD_CONTACT_XLSX_URL": str(row.get("artifact_xlsx_url") or ""),
        "UF_CRM_GRAMLEAD_CONTACT_DOCX_URL": str(row.get("artifact_docx_url") or ""),
    }
    if phones:
        fields["PHONE"] = [{"VALUE": str(phone), "VALUE_TYPE": "WORK"} for phone in phones[:3]]
    if emails:
        fields["EMAIL"] = [{"VALUE": str(email), "VALUE_TYPE": "WORK"} for email in emails[:3]]
    company = str(row.get("company") or "").strip()
    if company:
        fields["COMPANY_TITLE"] = company[:250]
    return fields


def _lead_payload(row: Dict[str, Any], *, batch_id: str) -> Dict[str, Any]:
    contact_name = str(row.get("fio") or row.get("name") or row.get("sender_name") or "GramLead lead")
    text = str(row.get("latest_message_text") or row.get("text") or row.get("summary") or "")
    source = str(row.get("latest_lead") or row.get("lead") or row.get("source") or "")
    title = f"GramLead · {contact_name}"[:250]
    return {
        "TITLE": title,
        "COMMENTS": text[:3000],
        "SOURCE_DESCRIPTION": source,
        "UF_CRM_GRAMLEAD_EXTERNAL_ID": _stable_external_id(row, prefix="lead"),
        "UF_CRM_GRAMLEAD_SOURCE": source,
        "UF_CRM_GRAMLEAD_SOURCE_TITLE": str(row.get("source_title") or source),
        "UF_CRM_GRAMLEAD_TG_USERNAME": str(row.get("username") or row.get("sender_username") or ""),
        "UF_CRM_GRAMLEAD_TG_ID": str(row.get("sender_id") or row.get("telegram_id") or ""),
        "UF_CRM_GRAMLEAD_MESSAGE_ID": str(row.get("message_id") or ""),
        "UF_CRM_GRAMLEAD_SCORE": float(row.get("score") or 0),
        "UF_CRM_GRAMLEAD_LAST_MESSAGE_AT": str(row.get("last_message_at") or ""),
        "UF_CRM_GRAMLEAD_EXPORT_BATCH": batch_id,
    }


def _load_crm_contact_rows(limit: int) -> List[Dict[str, Any]]:
    try:
        from app.storage.duckdb_store import _duckdb_load_crm_rows

        rows = list(_duckdb_load_crm_rows(limit=max(1, limit)))
        if rows:
            return rows
    except Exception:
        pass
    rows = _load_message_rows_from_duckdb(limit=max(1, limit))
    if rows:
        return rows
    from app.repositories import legacy

    legacy.refresh_globals(globals(), setdefault=True)
    try:
        if "_duckdb_crm_ready" in globals() and _duckdb_crm_ready():  # type: ignore[name-defined]
            return list(_duckdb_load_crm_rows(limit=max(1, limit)))  # type: ignore[name-defined]
    except Exception:
        pass
    try:
        return list(_analysis_rows("crm", limit=max(1, limit)))  # type: ignore[name-defined]
    except Exception:
        return []


def _source_title_from_jsonl(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "GramLead source"
    name = Path(text).name
    if name.endswith(".jsonl"):
        name = name[:-6]
    return name or text


def _safe_slug(value: str, *, fallback: str = "contact") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9а-яё_-]+", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text[:80] or fallback


def _contact_identity_sql() -> str:
    return (
        "coalesce(nullif(cast(sender_id as varchar), ''), "
        "nullif(sender_username, ''), nullif(sender_name, ''), 'unknown')"
    )


def _duckdb_path_from_settings(settings: Optional[Dict[str, Any]] = None) -> Path:
    configured = ""
    if isinstance(settings, dict):
        configured = str(settings.get("duckdb_read_path") or "").strip()
    return Path(configured or str(DUCKDB_READ_PATH))


def _load_owner_app_settings() -> Dict[str, Any]:
    if not APP_SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _openrouter_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    owner = _load_owner_app_settings()
    owner_app_settings = owner.get("_app_settings") if isinstance(owner.get("_app_settings"), dict) else {}
    owner_settings = {**owner, **owner_app_settings}
    return {
        "api_key": str(settings.get("openrouter_api_key") or owner_settings.get("openrouter_api_key") or "").strip(),
        "model": str(settings.get("openrouter_model") or owner_settings.get("openrouter_model") or DEFAULT_OPENROUTER_MODEL_ID).strip(),
        "prompt": str(settings.get("openrouter_prompt") or DEFAULT_OPENROUTER_PROMPT).strip(),
        "timeout_sec": max(5.0, min(300.0, float(settings.get("openrouter_timeout_sec") or owner_settings.get("openrouter_timeout_sec") or 120.0))),
    }


def _xml_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _write_xlsx(path: Path, rows: List[Dict[str, Any]]) -> None:
    headers = ["Дата", "Message ID", "Username", "Имя", "Текст"]

    def cell(col: int, row_index: int, value: Any) -> str:
        col_name = ""
        n = col
        while n:
            n, rem = divmod(n - 1, 26)
            col_name = chr(65 + rem) + col_name
        return (
            f'<c r="{col_name}{row_index}" t="inlineStr"><is><t>'
            f"{_xml_escape(value)}"
            "</t></is></c>"
        )

    sheet_rows = []
    sheet_rows.append("<row r=\"1\">" + "".join(cell(idx + 1, 1, header) for idx, header in enumerate(headers)) + "</row>")
    for row_number, item in enumerate(rows, start=2):
        values = [
            item.get("date_utc_raw") or item.get("date_utc") or "",
            item.get("message_id") or "",
            item.get("sender_username") or "",
            item.get("sender_name") or "",
            item.get("text") or "",
        ]
        sheet_rows.append(
            f'<row r="{row_number}">' + "".join(cell(idx + 1, row_number, value) for idx, value in enumerate(values)) + "</row>"
        )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "_rels/.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "xl/workbook.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="messages" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _write_docx(path: Path, *, contact: Dict[str, Any], openrouter_answer: str, prompt: str) -> None:
    paragraphs = [
        "GramLead: OpenRouter анализ контакта",
        f"Контакт: {contact.get('fio') or contact.get('name') or contact.get('contact_key') or ''}",
        f"Источник: {contact.get('source_title') or contact.get('source') or ''}",
        "Промт:",
        prompt,
        "Ответ OpenRouter:",
        openrouter_answer or "OpenRouter ответ не получен.",
    ]
    body = "".join(f"<w:p><w:r><w:t>{_xml_escape(text)}</w:t></w:r></w:p>" for text in paragraphs)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "_rels/.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr("word/document.xml", document_xml)


def _artifact_url(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(ARTIFACTS_DIR.resolve())
    except Exception:
        relative = Path(path.name)
    return f"{PUBLIC_BASE_URL}/files/{'/'.join(relative.parts)}"


def _write_contact_message_artifacts(
    contact: Dict[str, Any],
    messages: List[Dict[str, Any]],
    *,
    openrouter_answer: str = "",
    openrouter_prompt: str = DEFAULT_OPENROUTER_PROMPT,
) -> Dict[str, Any]:
    contact_key = str(contact.get("contact_key") or contact.get("id") or uuid4().hex)
    digest = hashlib.sha256(contact_key.encode("utf-8")).hexdigest()[:16]
    slug = _safe_slug(str(contact.get("fio") or contact.get("username") or contact_key))
    folder = ARTIFACTS_DIR / f"{slug}-{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    jsonl_path = folder / "messages.jsonl"
    html_path = folder / "messages.html"
    xlsx_path = folder / "messages.xlsx"
    docx_path = folder / "openrouter-answer.docx"
    jsonl_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in messages) + ("\n" if messages else ""),
        encoding="utf-8",
    )
    rows_html = "\n".join(
        "<tr>"
        f"<td>{_xml_escape(item.get('date_utc_raw') or item.get('date_utc') or '')}</td>"
        f"<td>{_xml_escape(item.get('message_id') or '')}</td>"
        f"<td>{_xml_escape(item.get('sender_username') or item.get('sender_name') or '')}</td>"
        f"<td>{_xml_escape(item.get('text') or '')}</td>"
        "</tr>"
        for item in messages
    )
    html_path.write_text(
        (
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>GramLead contact messages</title>"
            "<style>body{font-family:Arial,sans-serif;margin:24px;color:#0f172a}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #dbe3ef;padding:8px;vertical-align:top}"
            "pre{white-space:pre-wrap;background:#f8fafc;border:1px solid #dbe3ef;padding:12px;border-radius:8px}</style></head><body>"
            f"<h1>{_xml_escape(contact.get('fio') or contact.get('contact_key') or 'GramLead contact')}</h1>"
            f"<p>Сообщений: {len(messages)}</p>"
            f"<h2>OpenRouter</h2><pre>{_xml_escape(openrouter_answer or 'OpenRouter ответ не получен.')}</pre>"
            "<h2>Сообщения</h2><table><thead><tr><th>Дата</th><th>ID</th><th>Автор</th><th>Текст</th></tr></thead><tbody>"
            f"{rows_html}</tbody></table></body></html>"
        ),
        encoding="utf-8",
    )
    _write_xlsx(xlsx_path, messages)
    _write_docx(docx_path, contact=contact, openrouter_answer=openrouter_answer, prompt=openrouter_prompt)
    return {
        "messages_count": len(messages),
        "jsonl_path": str(jsonl_path),
        "html_path": str(html_path),
        "xlsx_path": str(xlsx_path),
        "docx_path": str(docx_path),
        "jsonl_url": _artifact_url(jsonl_path),
        "html_url": _artifact_url(html_path),
        "xlsx_url": _artifact_url(xlsx_path),
        "docx_url": _artifact_url(docx_path),
    }


def _call_openrouter_for_contact(contact: Dict[str, Any], messages: List[Dict[str, Any]], settings: Dict[str, Any]) -> str:
    openrouter = _openrouter_settings(settings)
    api_key = openrouter["api_key"]
    if not api_key:
        return "OpenRouter не запущен: API key не настроен."
    context_rows = []
    for item in messages[-80:]:
        text = str(item.get("text") or "").strip()
        if text:
            context_rows.append(
                f"{item.get('date_utc_raw') or ''} · @{item.get('sender_username') or item.get('sender_name') or 'unknown'}: {text[:1200]}"
            )
    if not context_rows:
        return "OpenRouter не запущен: у контакта нет текстовых сообщений."
    payload = {
        "model": openrouter["model"],
        "messages": [
            {
                "role": "system",
                "content": "Ты CRM-аналитик GramLead. Отвечай по-русски, коротко, без выдуманных фактов.",
            },
            {
                "role": "user",
                "content": (
                    f"Контакт: {contact.get('fio') or contact.get('contact_key')}\n"
                    f"Источник: {contact.get('source_title') or contact.get('source') or ''}\n"
                    f"Промт владельца:\n{openrouter['prompt']}\n\n"
                    "Сообщения контакта:\n" + "\n".join(context_rows)
                ),
            },
        ],
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 1200,
    }
    request = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://127.0.0.1:8024",
            "X-Title": "GramLead Bitrix24 Export",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(openrouter["timeout_sec"])) as response:
            parsed = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        return str((((parsed.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
    except Exception as exc:
        return f"OpenRouter ошибка: {exc}"


def _load_contact_messages_from_duckdb(
    conn: Any,
    *,
    source_jsonl: str,
    contact_identity: str,
    max_messages: int = 5000,
) -> List[Dict[str, Any]]:
    identity_sql = _contact_identity_sql()
    raw_rows = conn.execute(
        f"""
        SELECT source_jsonl, message_id, date_utc_raw, text, sender_username, sender_name, sender_id
        FROM messages_raw
        WHERE source_jsonl = ?
          AND {identity_sql} = ?
          AND coalesce(text, '') <> ''
        ORDER BY coalesce(date_utc_raw, ''), message_id
        LIMIT ?
        """,
        [source_jsonl, contact_identity, max(1, int(max_messages or 5000))],
    ).fetchall()
    return [
        {
            "source_jsonl": str(row[0] or ""),
            "message_id": int(row[1] or 0),
            "date_utc_raw": str(row[2] or ""),
            "text": str(row[3] or ""),
            "sender_username": str(row[4] or ""),
            "sender_name": str(row[5] or ""),
            "sender_id": str(row[6] or ""),
        }
        for row in raw_rows
    ]


def _load_message_rows_from_duckdb(limit: int) -> List[Dict[str, Any]]:
    state = _load_state()
    settings = state.get("settings") or {}
    duckdb_path = _duckdb_path_from_settings(settings)
    if not duckdb_path.exists():
        return []
    try:
        import duckdb

        conn = duckdb.connect(str(duckdb_path), read_only=True)
        try:
            raw_rows = conn.execute(
                f"""
                SELECT
                    source_jsonl,
                    {_contact_identity_sql()} AS contact_identity,
                    max(sender_id) AS sender_id,
                    max(sender_username) AS sender_username,
                    max(sender_name) AS sender_name,
                    max(date_utc_raw) AS last_message_at,
                    count(*) AS messages_count,
                    max(message_id) AS message_id
                FROM messages_raw
                WHERE coalesce(text, '') <> ''
                GROUP BY source_jsonl, contact_identity
                ORDER BY coalesce(max(date_utc_raw), '') DESC, max(message_id) DESC
                LIMIT ?
                """,
                [max(1, int(limit or 1))],
            ).fetchall()
            rows: List[Dict[str, Any]] = []
            openrouter_limit = max(0, int(settings.get("openrouter_contact_limit") or 10))
            for index, row in enumerate(raw_rows):
                source_jsonl = str(row[0] or "")
                source_title = _source_title_from_jsonl(source_jsonl)
                contact_identity = str(row[1] or "")
                sender_id = str(row[2] or "")
                sender_username = str(row[3] or "").strip()
                sender_name = str(row[4] or "").strip()
                contact_key = f"telegram:{source_title}:{contact_identity}"
                messages = _load_contact_messages_from_duckdb(conn, source_jsonl=source_jsonl, contact_identity=contact_identity)
                contact = {
                    "contact_key": contact_key,
                    "fio": sender_name or sender_username or contact_identity or "GramLead contact",
                    "username": sender_username,
                    "sender_id": sender_id,
                    "phones": [],
                    "emails": [],
                    "latest_lead": source_title,
                    "source": source_title,
                    "source_title": source_title,
                    "latest_message_text": str(messages[-1].get("text") if messages else ""),
                    "message_id": int(row[7] or 0),
                    "score": 0,
                    "last_message_at": str(row[5] or ""),
                    "messages_count": int(row[6] or len(messages)),
                    "source_jsonl": source_jsonl,
                }
                openrouter_answer = _call_openrouter_for_contact(contact, messages, settings) if index < openrouter_limit else ""
                artifacts = _write_contact_message_artifacts(
                    contact,
                    messages,
                    openrouter_answer=openrouter_answer,
                    openrouter_prompt=str(settings.get("openrouter_prompt") or DEFAULT_OPENROUTER_PROMPT),
                )
                contact.update(
                    {
                        "openrouter_answer": openrouter_answer,
                        "artifact_jsonl_url": artifacts["jsonl_url"],
                        "artifact_html_url": artifacts["html_url"],
                        "artifact_xlsx_url": artifacts["xlsx_url"],
                        "artifact_docx_url": artifacts["docx_url"],
                        "artifact_jsonl_path": artifacts["jsonl_path"],
                        "artifact_html_path": artifacts["html_path"],
                        "artifact_xlsx_path": artifacts["xlsx_path"],
                        "artifact_docx_path": artifacts["docx_path"],
                    }
                )
                rows.append(contact)
            return rows
        finally:
            conn.close()
    except Exception:
        return []


def dry_run(payload: Optional[Bitrix24RunPayload] = None) -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    options = payload or Bitrix24RunPayload(dry_run=True, limit=int(settings.get("dry_run_limit") or 25))
    limit = max(1, min(50000, int(options.limit or 25)))
    batch_id = f"dry_{uuid4().hex[:12]}"
    rows = _load_crm_contact_rows(limit)
    contact_payloads = [_contact_payload(row, batch_id=batch_id) for row in rows[:limit]]
    lead_payloads = [_lead_payload(row, batch_id=batch_id) for row in rows[:limit]]
    return {
        "ok": True,
        "dry_run": True,
        "message": f"Dry-run Bitrix24 готов: контактов {len(contact_payloads)}, лидов {len(lead_payloads)}.",
        "counts": {
            "source_rows": len(rows),
            "contacts": len(contact_payloads) if options.export_contacts else 0,
            "leads": len(lead_payloads) if options.export_leads else 0,
            "timeline_comments": len(lead_payloads) if options.export_timeline else 0,
        },
        "sample": {
            "contact": contact_payloads[0] if contact_payloads and options.export_contacts else None,
            "lead": lead_payloads[0] if lead_payloads and options.export_leads else None,
        },
        "settings": _safe_settings(settings),
    }


def run_export(payload: Bitrix24RunPayload) -> Dict[str, Any]:
    if payload.dry_run:
        return dry_run(payload)
    state = _load_state()
    settings = state.get("settings") or {}
    job_id = f"bitrix24_{uuid4().hex[:12]}"
    started_at = utc_now()
    rows = _load_crm_contact_rows(payload.limit)
    total_steps = (
        (len(rows) if payload.export_contacts else 0)
        + (len(rows) if payload.export_leads else 0)
        + (len(rows) if payload.export_timeline else 0)
    )
    job = {
        "job_id": job_id,
        "provider": "bitrix24",
        "status": "running",
        "started_at": started_at,
        "updated_at": started_at,
        "finished_at": None,
        "progress_percent": 0,
        "total": total_steps,
        "done": 0,
        "errors": [],
        "message": "Bitrix24 export запущен.",
        "dry_run": False,
    }
    state.setdefault("jobs", {})[job_id] = job
    _save_state(state)
    # Synchronous MVP: keeps the endpoint deterministic until a dedicated Celery
    # provider worker is introduced. It still preserves progress and mappings.
    result = _execute_export_job(job_id, rows=rows, payload=payload)
    return result


def _execute_export_job(job_id: str, *, rows: List[Dict[str, Any]], payload: Bitrix24RunPayload) -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    job = dict((state.get("jobs") or {}).get(job_id) or {})
    mappings = list(state.get("mappings") or [])
    client = Bitrix24Client(settings)
    total = max(1, int(job.get("total") or 1))
    done = 0
    errors: List[Dict[str, Any]] = []

    def _record_mapping(entity_type: str, external_id: str, external_entity_id: Any, payload_obj: Dict[str, Any]) -> None:
        checksum = hashlib.sha256(json.dumps(payload_obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        mappings.append(
            {
                "provider": "bitrix24",
                "gramlead_entity_type": entity_type,
                "gramlead_entity_id": external_id,
                "external_entity_type": entity_type,
                "external_entity_id": str(external_entity_id or ""),
                "external_url": "",
                "exported_at": utc_now(),
                "checksum": checksum,
            }
        )

    def _existing_external_entity_id(entity_type: str, external_id: str) -> str:
        for item in reversed(mappings):
            if (
                str(item.get("provider") or "") == "bitrix24"
                and str(item.get("gramlead_entity_type") or "") == entity_type
                and str(item.get("gramlead_entity_id") or "") == external_id
            ):
                return str(item.get("external_entity_id") or "").strip()
        return ""

    def _extract_external_id(response: Dict[str, Any], entity_type: str) -> Any:
        result = response.get("result")
        if isinstance(result, dict):
            item = result.get("item")
            if isinstance(item, dict):
                return item.get("id")
            return result.get("ID") or result.get("id")
        return result

    def _add_contact_timeline_comment(contact_id: Any, row: Dict[str, Any]) -> None:
        if not contact_id:
            return
        comment = _contact_timeline_comment(row)
        if not comment:
            return
        try:
            client.call(
                "crm.timeline.comment.add",
                {"fields": {"ENTITY_ID": str(contact_id), "ENTITY_TYPE": "contact", "COMMENT": comment}},
            )
        except Bitrix24Error as first_exc:
            if first_exc.code not in {"INVALID_ENTITY_TYPE", "ERROR_CORE"}:
                raise
            client.call(
                "crm.timeline.comment.add",
                {"fields": {"ENTITY_ID": str(contact_id), "ENTITY_TYPE": "CONTACT", "COMMENT": comment}},
            )

    try:
        for row in rows:
            contact_external_entity_id: Any = ""
            if payload.export_contacts:
                contact = _contact_payload(row, batch_id=job_id)
                external_id = str(contact["UF_CRM_GRAMLEAD_EXTERNAL_ID"])
                try:
                    existing_id = _existing_external_entity_id("contact", external_id)
                    if existing_id:
                        response = client.call("crm.contact.update", {"id": existing_id, "fields": contact})
                        response_external_id = existing_id
                    else:
                        response = client.call("crm.contact.add", {"fields": contact})
                        response_external_id = _extract_external_id(response, "contact")
                    contact_external_entity_id = response_external_id
                    _record_mapping("contact", external_id, response_external_id, contact)
                except Bitrix24Error as exc:
                    errors.append({"entity": external_id, "error": str(exc), "code": exc.code})
                done += 1
            if payload.export_leads:
                lead = _lead_payload(row, batch_id=job_id)
                external_id = str(lead["UF_CRM_GRAMLEAD_EXTERNAL_ID"])
                try:
                    try:
                        response = client.call("crm.item.add", {"entityTypeId": 1, "fields": lead})
                    except Bitrix24Error as universal_exc:
                        if universal_exc.status != 400:
                            raise
                        response = client.call("crm.lead.add", {"fields": lead})
                    _record_mapping("lead", external_id, _extract_external_id(response, "lead"), lead)
                except Bitrix24Error as exc:
                    errors.append({"entity": external_id, "error": str(exc), "code": exc.code})
                done += 1
            if payload.export_timeline:
                if payload.export_contacts and contact_external_entity_id:
                    try:
                        _add_contact_timeline_comment(contact_external_entity_id, row)
                    except Bitrix24Error as exc:
                        errors.append({"entity": str(contact_external_entity_id), "error": str(exc), "code": exc.code, "scope": "timeline"})
                done += 1
            job["done"] = done
            job["progress_percent"] = round((done / total) * 100, 1)
            job["updated_at"] = utc_now()
        job["status"] = "error" if errors else "done"
        job["message"] = "Bitrix24 export завершён с ошибками." if errors else "Bitrix24 export завершён."
    except Exception as exc:
        job["status"] = "error"
        errors.append({"entity": "job", "error": str(exc), "code": "job_error"})
        job["message"] = f"Bitrix24 export остановлен: {exc}"
    job["finished_at"] = utc_now()
    job["errors"] = errors[:50]
    state["mappings"] = mappings[-5000:]
    state.setdefault("jobs", {})[job_id] = job
    _save_state(state)
    return {"ok": job["status"] == "done", "job": job, "mappings_count": len(mappings)}


def cancel_job(job_id: str) -> Dict[str, Any]:
    state = _load_state()
    job = dict((state.get("jobs") or {}).get(job_id) or {})
    if not job:
        return {"ok": False, "message": "Bitrix24 job не найден", "job_id": job_id}
    if job.get("status") == "running":
        job["status"] = "cancelled"
        job["updated_at"] = utc_now()
        job["message"] = "Bitrix24 job отменён пользователем."
        state.setdefault("jobs", {})[job_id] = job
        _save_state(state)
    return {"ok": True, "job": job}


def get_job(job_id: str) -> Dict[str, Any]:
    state = _load_state()
    job = (state.get("jobs") or {}).get(job_id)
    return {"ok": bool(job), "job": job, "job_id": job_id}


def list_mappings() -> Dict[str, Any]:
    state = _load_state()
    items = list(state.get("mappings") or [])
    return {"ok": True, "items": items[-200:], "total": len(items)}


def list_jobs() -> Dict[str, Any]:
    state = _load_state()
    jobs = list((state.get("jobs") or {}).values())
    jobs.sort(key=lambda item: str(item.get("updated_at") or item.get("started_at") or ""), reverse=True)
    return {"ok": True, "items": jobs[:50], "total": len(jobs)}
