"""amoCRM export provider for GramLead CRM data."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.runtime_paths import CACHE_DIR

JobStatus = Literal["created", "running", "done", "cancelled", "error"]

STATE_PATH = CACHE_DIR / "crm_exports" / "amocrm.json"

GRAMLEAD_CUSTOM_FIELDS = [
    {"name": "GramLead External ID", "code": "GRAMLEAD_EXTERNAL_ID", "type": "text"},
    {"name": "Telegram Username", "code": "GRAMLEAD_TG_USERNAME", "type": "text"},
    {"name": "Telegram ID", "code": "GRAMLEAD_TG_ID", "type": "text"},
    {"name": "GramLead Source", "code": "GRAMLEAD_SOURCE", "type": "text"},
    {"name": "Last Message At", "code": "GRAMLEAD_LAST_MESSAGE_AT", "type": "date_time"},
    {"name": "GramLead Message ID", "code": "GRAMLEAD_MESSAGE_ID", "type": "text"},
    {"name": "GramLead Score", "code": "GRAMLEAD_SCORE", "type": "numeric"},
    {"name": "LLM Recommendation Short", "code": "GRAMLEAD_LLM_RECOMMENDATION", "type": "textarea"},
    {"name": "GramLead Export Batch", "code": "GRAMLEAD_EXPORT_BATCH", "type": "text"},
]


class AmoCrmConnectionPayload(BaseModel):
    subdomain: str = ""
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    access_token: str = ""
    refresh_token: str = ""
    selected_pipeline_id: str = ""
    selected_status_id: str = ""
    responsible_user_id: str = ""
    dry_run_limit: int = Field(default=25, ge=1, le=500)


class AmoCrmRunPayload(BaseModel):
    dry_run: bool = False
    limit: int = Field(default=100, ge=1, le=5000)
    export_contacts: bool = True
    export_companies: bool = False
    export_leads: bool = True
    export_notes: bool = True
    export_tags: bool = True


class AmoCrmError(RuntimeError):
    def __init__(self, message: str, *, code: str = "", status: int = 0, raw: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.raw = raw


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> Dict[str, Any]:
    return {
        "settings": {
            "subdomain": "",
            "client_id": "",
            "client_secret": "",
            "redirect_uri": "",
            "access_token": "",
            "refresh_token": "",
            "selected_pipeline_id": "",
            "selected_status_id": "",
            "responsible_user_id": "",
            "dry_run_limit": 25,
        },
        "capabilities": {},
        "custom_fields": [],
        "jobs": {},
        "mappings": [],
        "connection_checks": [],
        "updated_at": None,
    }


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return _default_state()
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state = _default_state()
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in state:
                    state[key] = value
        if not isinstance(state.get("settings"), dict):
            state["settings"] = _default_state()["settings"]
        return state
    except Exception:
        return _default_state()


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
        return f"{text[:2]}...{text[-2:]}"
    return f"{text[:6]}...{text[-4:]}"


def _normalize_subdomain(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urllib.parse.urlparse(text)
        return parsed.netloc or parsed.path
    return text


def _safe_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(settings or {})
    safe["client_secret_configured"] = bool(str(safe.get("client_secret") or "").strip())
    safe["access_token_configured"] = bool(str(safe.get("access_token") or "").strip())
    safe["refresh_token_configured"] = bool(str(safe.get("refresh_token") or "").strip())
    safe["client_secret_masked"] = _mask_secret(str(safe.get("client_secret") or ""))
    safe["access_token_masked"] = _mask_secret(str(safe.get("access_token") or ""))
    safe["refresh_token_masked"] = _mask_secret(str(safe.get("refresh_token") or ""))
    for key in ("client_secret", "access_token", "refresh_token"):
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


def save_settings(payload: AmoCrmConnectionPayload) -> Dict[str, Any]:
    state = _load_state()
    current = dict(state.get("settings") or {})
    incoming = payload.model_dump()
    for key, value in incoming.items():
        if key in {"client_secret", "access_token", "refresh_token"} and not str(value or "").strip():
            continue
        current[key] = str(value).strip() if isinstance(value, str) else value
    current["subdomain"] = _normalize_subdomain(str(current.get("subdomain") or ""))
    current["dry_run_limit"] = max(1, min(500, int(current.get("dry_run_limit") or 25)))
    state["settings"] = current
    _save_state(state)
    return {
        "ok": True,
        "message": "Настройки amoCRM сохранены. Токены замаскированы и не возвращаются во frontend.",
        "settings": _safe_settings(current),
    }


class AmoCrmClient:
    def __init__(self, settings: Dict[str, Any], *, timeout_sec: float = 20.0) -> None:
        self.settings = settings
        self.timeout_sec = timeout_sec

    def _base_url(self) -> str:
        subdomain = _normalize_subdomain(str(self.settings.get("subdomain") or ""))
        if not subdomain:
            raise AmoCrmError("amoCRM subdomain не задан", code="missing_subdomain")
        return f"https://{subdomain}"

    def _method_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return f"{self._base_url()}{normalized}"

    def call(self, method: str, path: str, payload: Optional[Any] = None) -> Dict[str, Any]:
        token = str(self.settings.get("access_token") or "").strip()
        if not token:
            raise AmoCrmError("amoCRM access token не задан", code="missing_access_token")
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._method_url(path),
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/hal+json, application/json",
                "Authorization": f"Bearer {token}",
            },
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise AmoCrmError(
                _normalize_error_message(raw) or f"amoCRM HTTP {exc.code}",
                code="http_error",
                status=exc.code,
                raw=raw,
            ) from exc
        except Exception as exc:
            raise AmoCrmError(f"amoCRM network error: {exc}", code="network_error") from exc
        if not body:
            return {}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AmoCrmError("amoCRM вернул не JSON ответ", code="invalid_json", raw=body) from exc
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    def refresh_access_token(self) -> Dict[str, Any]:
        client_id = str(self.settings.get("client_id") or "").strip()
        client_secret = str(self.settings.get("client_secret") or "").strip()
        refresh_token = str(self.settings.get("refresh_token") or "").strip()
        redirect_uri = str(self.settings.get("redirect_uri") or "").strip()
        if not all([client_id, client_secret, refresh_token, redirect_uri]):
            raise AmoCrmError("Для refresh token нужны client_id, client_secret, redirect_uri и refresh_token", code="missing_oauth_refresh_fields")
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": redirect_uri,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._method_url("/oauth2/access_token"),
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                body = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise AmoCrmError(f"amoCRM token refresh failed: {exc}", code="token_refresh_error") from exc
        parsed = json.loads(body or "{}")
        if not isinstance(parsed, dict) or not parsed.get("access_token"):
            raise AmoCrmError("amoCRM token refresh вернул ответ без access_token", code="token_refresh_invalid")
        return parsed


def _normalize_error_message(raw: Any) -> str:
    if isinstance(raw, dict):
        detail = raw.get("detail") or raw.get("title") or raw.get("error_description") or raw.get("error")
        return str(detail or "").strip()
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
    account = result or {}
    return {
        "subdomain": settings.get("subdomain") or "",
        "account_id": account.get("id") or account.get("account_id"),
        "leads_supported": True,
        "contacts_supported": True,
        "companies_supported": True,
        "notes_supported": True,
        "custom_fields_setup_supported": True,
        "checked_at": utc_now(),
    }


def test_connection() -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    check = {
        "ts": utc_now(),
        "subdomain": settings.get("subdomain") or "",
        "ok": False,
        "error": "",
    }
    try:
        client = AmoCrmClient(settings)
        account = client.call("GET", "/api/v4/account")
        capabilities = _build_capabilities(settings, account)
        state["capabilities"] = capabilities
        check["ok"] = True
        check["result"] = "account ok"
        message = "Подключение amoCRM проверено: account доступен."
    except AmoCrmError as exc:
        check["error"] = f"{exc.code}: {exc}"
        capabilities = _build_capabilities(settings)
        state["capabilities"] = capabilities
        message = f"amoCRM не проверен: {exc}"
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


def _amocrm_custom_field_payload(field: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": str(field.get("name") or ""),
        "code": str(field.get("code") or ""),
        "type": str(field.get("type") or "text"),
    }


def setup_custom_fields(dry_run: bool = False) -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    target_paths = {
        "contacts": "/api/v4/contacts/custom_fields",
        "leads": "/api/v4/leads/custom_fields",
    }
    fields = []
    errors = []
    client = None if dry_run else AmoCrmClient(settings)
    for entity, path in target_paths.items():
        existing_codes = set()
        if client is not None:
            try:
                listed = client.call("GET", path)
                embedded = (listed.get("_embedded") or {}).get("custom_fields") or []
                existing_codes = {str(item.get("code") or item.get("name") or "") for item in embedded if isinstance(item, dict)}
            except AmoCrmError as exc:
                errors.append({"entity": entity, "path": path, "error": str(exc), "code": exc.code})
        for item in GRAMLEAD_CUSTOM_FIELDS:
            code = str(item.get("code") or "")
            record = dict(item, entity=entity, status="planned" if dry_run else "exists" if code in existing_codes else "created")
            if client is not None and code not in existing_codes:
                try:
                    response = client.call("POST", path, [_amocrm_custom_field_payload(item)])
                    record["amocrm_result"] = response.get("_embedded") or response
                except AmoCrmError as exc:
                    record["status"] = "error"
                    record["error"] = str(exc)
                    errors.append({"entity": entity, "field": code, "path": path, "error": str(exc), "code": exc.code})
            fields.append(record)
    if not dry_run:
        state["custom_fields"] = fields
        state["custom_fields_errors"] = errors[-100:]
        _save_state(state)
    return {
        "ok": not errors,
        "dry_run": bool(dry_run),
        "message": (
            "Поля GramLead для amoCRM подготовлены."
            if not errors and not dry_run
            else "Dry-run: поля amoCRM будут подготовлены."
            if dry_run
            else "Поля amoCRM подготовлены частично: есть ошибки, проверьте права."
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


def _custom_value(name: str, value: Any) -> Dict[str, Any]:
    return {"field_name": name, "values": [{"value": str(value or "")}]}


def _contact_payload(row: Dict[str, Any], *, batch_id: str) -> Dict[str, Any]:
    name = str(row.get("fio") or row.get("name") or row.get("sender_name") or row.get("contact_key") or "GramLead contact")
    phones = row.get("phones") if isinstance(row.get("phones"), list) else []
    emails = row.get("emails") if isinstance(row.get("emails"), list) else []
    fields = [
        _custom_value("GramLead External ID", _stable_external_id(row)),
        _custom_value("Telegram Username", row.get("username") or row.get("sender_username") or ""),
        _custom_value("Telegram ID", row.get("sender_id") or row.get("telegram_id") or ""),
        _custom_value("GramLead Source", row.get("latest_lead") or row.get("lead") or row.get("source") or ""),
        _custom_value("Last Message At", row.get("last_message_at") or ""),
        _custom_value("GramLead Export Batch", batch_id),
    ]
    if phones:
        fields.append({"field_code": "PHONE", "values": [{"value": str(phone), "enum_code": "WORK"} for phone in phones[:3]]})
    if emails:
        fields.append({"field_code": "EMAIL", "values": [{"value": str(email), "enum_code": "WORK"} for email in emails[:3]]})
    return {
        "name": name[:250],
        "custom_fields_values": fields,
        "_embedded": {"tags": [{"name": "gramlead"}]},
    }


def _lead_payload(row: Dict[str, Any], *, batch_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    contact_name = str(row.get("fio") or row.get("name") or row.get("sender_name") or "GramLead lead")
    source = str(row.get("latest_lead") or row.get("lead") or row.get("source") or "")
    payload: Dict[str, Any] = {
        "name": f"GramLead · {contact_name}"[:250],
        "custom_fields_values": [
            _custom_value("GramLead External ID", _stable_external_id(row, prefix="lead")),
            _custom_value("GramLead Source", source),
            _custom_value("GramLead Message ID", row.get("message_id") or ""),
            _custom_value("GramLead Score", row.get("score") or 0),
            _custom_value("LLM Recommendation Short", str(row.get("recommendation") or row.get("summary") or "")[:500]),
            _custom_value("GramLead Export Batch", batch_id),
        ],
        "_embedded": {"tags": [{"name": "gramlead"}]},
    }
    for key, target in (("selected_pipeline_id", "pipeline_id"), ("selected_status_id", "status_id"), ("responsible_user_id", "responsible_user_id")):
        value = str(settings.get(key) or "").strip()
        if value.isdigit():
            payload[target] = int(value)
    return payload


def _note_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    text = str(row.get("latest_message_text") or row.get("text") or row.get("summary") or "")
    return {"note_type": "common", "params": {"text": f"GramLead context:\n{text[:5000]}"}}


def _load_crm_contact_rows(limit: int) -> List[Dict[str, Any]]:
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


def dry_run(payload: Optional[AmoCrmRunPayload] = None) -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    options = payload or AmoCrmRunPayload(dry_run=True, limit=int(settings.get("dry_run_limit") or 25))
    limit = max(1, min(5000, int(options.limit or 25)))
    batch_id = f"dry_{uuid4().hex[:12]}"
    rows = _load_crm_contact_rows(limit)
    contacts = [_contact_payload(row, batch_id=batch_id) for row in rows[:limit]]
    leads = [_lead_payload(row, batch_id=batch_id, settings=settings) for row in rows[:limit]]
    notes = [_note_payload(row) for row in rows[:limit]]
    return {
        "ok": True,
        "dry_run": True,
        "message": f"Dry-run amoCRM готов: контактов {len(contacts)}, сделок {len(leads)}.",
        "counts": {
            "source_rows": len(rows),
            "contacts": len(contacts) if options.export_contacts else 0,
            "companies": 0,
            "leads": len(leads) if options.export_leads else 0,
            "notes": len(notes) if options.export_notes else 0,
            "tags": len(leads) if options.export_tags else 0,
        },
        "sample": {
            "contact": contacts[0] if contacts and options.export_contacts else None,
            "lead": leads[0] if leads and options.export_leads else None,
            "note": notes[0] if notes and options.export_notes else None,
        },
        "settings": _safe_settings(settings),
    }


def run_export(payload: AmoCrmRunPayload) -> Dict[str, Any]:
    if payload.dry_run:
        return dry_run(payload)
    state = _load_state()
    settings = state.get("settings") or {}
    job_id = f"amocrm_{uuid4().hex[:12]}"
    started_at = utc_now()
    rows = _load_crm_contact_rows(payload.limit)
    total_steps = (
        (len(rows) if payload.export_contacts else 0)
        + (len(rows) if payload.export_leads else 0)
        + (len(rows) if payload.export_notes else 0)
    )
    job = {
        "job_id": job_id,
        "provider": "amocrm",
        "status": "running",
        "started_at": started_at,
        "updated_at": started_at,
        "finished_at": None,
        "progress_percent": 0,
        "total": total_steps,
        "done": 0,
        "errors": [],
        "message": "amoCRM export запущен.",
        "dry_run": False,
    }
    state.setdefault("jobs", {})[job_id] = job
    _save_state(state)
    return _execute_export_job(job_id, rows=rows, payload=payload)


def _execute_export_job(job_id: str, *, rows: List[Dict[str, Any]], payload: AmoCrmRunPayload) -> Dict[str, Any]:
    state = _load_state()
    settings = state.get("settings") or {}
    job = dict((state.get("jobs") or {}).get(job_id) or {})
    mappings = list(state.get("mappings") or [])
    client = AmoCrmClient(settings)
    total = max(1, int(job.get("total") or 1))
    done = 0
    errors: List[Dict[str, Any]] = []

    def _record_mapping(entity_type: str, external_id: str, external_entity_id: Any, payload_obj: Dict[str, Any]) -> None:
        checksum = hashlib.sha256(json.dumps(payload_obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        mappings.append(
            {
                "provider": "amocrm",
                "gramlead_entity_type": entity_type,
                "gramlead_entity_id": external_id,
                "external_entity_type": entity_type,
                "external_entity_id": str(external_entity_id or ""),
                "external_url": "",
                "exported_at": utc_now(),
                "checksum": checksum,
            }
        )

    try:
        for row in rows:
            lead_id = None
            if payload.export_contacts:
                contact = _contact_payload(row, batch_id=job_id)
                external_id = _stable_external_id(row)
                try:
                    response = client.call("POST", "/api/v4/contacts", [contact])
                    item = (((response.get("_embedded") or {}).get("contacts") or [{}])[0])
                    _record_mapping("contact", external_id, item.get("id"), contact)
                except AmoCrmError as exc:
                    errors.append({"entity": external_id, "error": str(exc), "code": exc.code})
                done += 1
            if payload.export_leads:
                lead = _lead_payload(row, batch_id=job_id, settings=settings)
                external_id = _stable_external_id(row, prefix="lead")
                try:
                    response = client.call("POST", "/api/v4/leads", [lead])
                    item = (((response.get("_embedded") or {}).get("leads") or [{}])[0])
                    lead_id = item.get("id")
                    _record_mapping("lead", external_id, lead_id, lead)
                except AmoCrmError as exc:
                    errors.append({"entity": external_id, "error": str(exc), "code": exc.code})
                done += 1
            if payload.export_notes:
                if lead_id:
                    try:
                        client.call("POST", f"/api/v4/leads/{lead_id}/notes", [_note_payload(row)])
                    except AmoCrmError as exc:
                        errors.append({"entity": str(lead_id), "error": str(exc), "code": exc.code})
                done += 1
            job["done"] = done
            job["progress_percent"] = round((done / total) * 100, 1)
            job["updated_at"] = utc_now()
        job["status"] = "error" if errors else "done"
        job["message"] = "amoCRM export завершён с ошибками." if errors else "amoCRM export завершён."
    except Exception as exc:
        job["status"] = "error"
        errors.append({"entity": "job", "error": str(exc), "code": "job_error"})
        job["message"] = f"amoCRM export остановлен: {exc}"
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
        return {"ok": False, "message": "amoCRM job не найден", "job_id": job_id}
    if job.get("status") == "running":
        job["status"] = "cancelled"
        job["updated_at"] = utc_now()
        job["message"] = "amoCRM job отменён пользователем."
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
