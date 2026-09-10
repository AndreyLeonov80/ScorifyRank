"""Standalone CRM export UI/API app.

This app is used by the dedicated Docker containers:
- x-files-crm-bitrix24
- x-files-crm-amocrm

It intentionally exposes only CRM export settings/actions for one provider,
instead of the full GramLead backend surface.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.services.crm_exports import amocrm, bitrix24


PROVIDER = os.getenv("CRM_EXPORT_PROVIDER", "bitrix24").strip().lower()

if PROVIDER == "amocrm":
    provider_title = "amoCRM"
    provider_module = amocrm
    settings_model = amocrm.AmoCrmConnectionPayload
    run_model = amocrm.AmoCrmRunPayload
elif PROVIDER == "bitrix24":
    provider_title = "Bitrix24"
    provider_module = bitrix24
    settings_model = bitrix24.Bitrix24ConnectionPayload
    run_model = bitrix24.Bitrix24RunPayload
else:
    raise RuntimeError(f"Unsupported CRM_EXPORT_PROVIDER={PROVIDER!r}")

app = FastAPI(title=f"GramLead {provider_title} Export", version="1.0.0")


@app.get("/api/health")
def api_health() -> Dict[str, Any]:
    return {"ok": True, "provider": PROVIDER, "title": provider_title}


@app.get("/api/settings")
def api_settings() -> Dict[str, Any]:
    return provider_module.get_settings()


@app.post("/api/settings")
def api_save_settings(payload: settings_model):  # type: ignore[valid-type]
    return provider_module.save_settings(payload)


@app.post("/api/test")
def api_test() -> Dict[str, Any]:
    return provider_module.test_connection()


@app.post("/api/setup")
def api_setup(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return provider_module.setup_custom_fields(dry_run=bool((payload or {}).get("dry_run")))


@app.post("/api/dry-run")
def api_dry_run(payload: Optional[run_model] = None):  # type: ignore[valid-type]
    return provider_module.dry_run(payload)


@app.post("/api/run")
def api_run(payload: run_model):  # type: ignore[valid-type]
    return provider_module.run_export(payload)


@app.post("/api/cancel")
def api_cancel(payload: Dict[str, Any]) -> Dict[str, Any]:
    return provider_module.cancel_job(str(payload.get("job_id") or ""))


@app.get("/api/jobs")
def api_jobs() -> Dict[str, Any]:
    return provider_module.list_jobs()


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> Dict[str, Any]:
    return provider_module.get_job(job_id)


@app.get("/api/mappings")
def api_mappings() -> Dict[str, Any]:
    return provider_module.list_mappings()


@app.get("/files/{file_path:path}")
def api_files(file_path: str):
    artifacts_dir = getattr(provider_module, "ARTIFACTS_DIR", None)
    if artifacts_dir is None:
        return JSONResponse({"ok": False, "error": "files_not_supported"}, status_code=404)
    root = Path(artifacts_dir).resolve()
    target = (root / file_path).resolve()
    if root not in target.parents and target != root:
        return JSONResponse({"ok": False, "error": "invalid_path"}, status_code=400)
    if not target.exists() or not target.is_file():
        return JSONResponse({"ok": False, "error": "file_not_found"}, status_code=404)
    return FileResponse(target)


def _provider_fields() -> str:
    if PROVIDER == "amocrm":
        fields = [
            ("subdomain", "amoCRM subdomain", "company.amocrm.ru", "text"),
            ("client_id", "client_id", "", "text"),
            ("client_secret", "client_secret", "секрет уже настроен", "password"),
            ("redirect_uri", "redirect_uri", "https://example.com/amocrm/callback", "text"),
            ("access_token", "access_token", "секрет уже настроен", "password"),
            ("refresh_token", "refresh_token", "секрет уже настроен", "password"),
            ("selected_pipeline_id", "Pipeline ID", "", "text"),
            ("selected_status_id", "Status ID", "", "text"),
            ("responsible_user_id", "Responsible user ID", "", "text"),
            ("dry_run_limit", "Лимит dry-run/export", "25", "number"),
        ]
    else:
        fields = [
            ("portal_url", "Bitrix24 portal URL", "https://company.bitrix24.ru", "text"),
            ("auth_mode", "Auth mode: webhook/oauth", "webhook", "text"),
            ("webhook_url", "Webhook URL", "секрет уже настроен", "password"),
            ("access_token", "OAuth access token", "секрет уже настроен", "password"),
            ("client_id", "client_id", "", "text"),
            ("client_secret", "client_secret", "секрет уже настроен", "password"),
            ("refresh_token", "refresh_token", "секрет уже настроен", "password"),
            ("selected_entity", "Сущность: lead/deal", "lead", "text"),
            ("dry_run_limit", "Лимит dry-run/export", "25", "number"),
            ("duckdb_read_path", "DuckDB read path", "/data/db/duckdb/gramlead-read.duckdb", "text"),
            ("openrouter_api_key", "OpenRouter API key", "секрет уже настроен", "password"),
            ("openrouter_model", "OpenRouter model", "openai/gpt-oss-120b:free", "text"),
            ("openrouter_contact_limit", "OpenRouter контактов за запуск", "10", "number"),
            ("openrouter_timeout_sec", "OpenRouter timeout sec", "120", "number"),
            ("openrouter_prompt", "OpenRouter prompt", "Оцени вероятность покупки GramLead.", "textarea"),
        ]
    return "\n".join(
        f"""
        <label>
          <span>{label}</span>
          {'<textarea id="' + key + '" placeholder="' + placeholder + '"></textarea>' if input_type == 'textarea' else '<input id="' + key + '" type="' + input_type + '" placeholder="' + placeholder + '" />'}
        </label>
        """
        for key, label, placeholder, input_type in fields
    )


def _html() -> str:
    settings_keys = (
        [
            "subdomain",
            "client_id",
            "client_secret",
            "redirect_uri",
            "access_token",
            "refresh_token",
            "selected_pipeline_id",
            "selected_status_id",
            "responsible_user_id",
            "dry_run_limit",
        ]
        if PROVIDER == "amocrm"
        else [
            "portal_url",
            "auth_mode",
            "webhook_url",
            "access_token",
            "client_id",
            "client_secret",
            "refresh_token",
            "selected_entity",
            "dry_run_limit",
            "duckdb_read_path",
            "openrouter_api_key",
            "openrouter_model",
            "openrouter_contact_limit",
            "openrouter_timeout_sec",
            "openrouter_prompt",
        ]
    )
    export_flags = (
        ["export_contacts", "export_companies", "export_leads", "export_notes", "export_tags"]
        if PROVIDER == "amocrm"
        else ["export_contacts", "export_leads", "export_timeline"]
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GramLead {provider_title} Export</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, Arial, sans-serif; }}
    body {{ margin: 0; background: #eef5fb; color: #0f172a; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    header {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom: 20px; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    .muted {{ color:#64748b; }}
    .card {{ background: rgba(255,255,255,.92); border:1px solid #d9e4f2; border-radius:18px; padding:22px; box-shadow:0 16px 42px rgba(15,23,42,.08); margin-bottom:18px; }}
    .grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:14px; }}
    label span {{ display:block; font-weight:700; margin-bottom:6px; color:#475569; }}
    input, textarea {{ width:100%; box-sizing:border-box; border:1px solid #cbd5e1; border-radius:12px; padding:13px 14px; font-size:16px; background:#fff; }}
    textarea {{ min-height:120px; resize:vertical; grid-column:1/-1; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    button {{ border:1px solid #cbd5e1; border-radius:12px; padding:12px 16px; font-weight:800; background:#fff; color:#0f172a; cursor:pointer; }}
    button.primary {{ background:#2563eb; border-color:#2563eb; color:#fff; }}
    button:disabled {{ opacity:.55; cursor:wait; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }}
    .chip {{ display:flex; align-items:center; gap:8px; border:1px solid #cbd5e1; border-radius:999px; padding:9px 12px; background:#fff; }}
    .chip input {{ width:auto; }}
    pre {{ white-space:pre-wrap; overflow:auto; max-height:420px; background:#0f172a; color:#dbeafe; padding:16px; border-radius:14px; }}
    .badge {{ display:inline-flex; border-radius:999px; padding:8px 12px; background:#dcfce7; color:#166534; font-weight:800; }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>GramLead {provider_title} Export</h1>
      <div class="muted">Отдельный Docker-контейнер CRM export. Основной GramLead UI остаётся на <code>127.0.0.1:8008</code>.</div>
    </div>
    <span class="badge" id="status">loading</span>
  </header>

  <section class="card">
    <h2>Настройки API {provider_title}</h2>
    <div class="grid">{_provider_fields()}</div>
    <div class="chips" id="flags"></div>
    <div class="actions">
      <button class="primary" onclick="saveSettings()">Сохранить</button>
      <button onclick="runAction('test')">Проверить подключение</button>
      <button onclick="runAction('setup-dry')">Dry-run полей</button>
      <button onclick="runAction('setup')">Подготовить поля</button>
      <button onclick="runAction('dry-run')">Dry-run экспорта</button>
      <button class="primary" onclick="runAction('run')">Экспортировать</button>
    </div>
  </section>

  <section class="card">
    <h2>Ответ</h2>
    <pre id="result">{{}}</pre>
  </section>
</main>
<script>
const provider = {json.dumps(PROVIDER)};
const settingsKeys = {json.dumps(settings_keys)};
const exportFlags = {json.dumps(export_flags)};
let busy = false;

function setBusy(value) {{
  busy = value;
  document.querySelectorAll('button').forEach((button) => button.disabled = value);
  document.getElementById('status').textContent = value ? 'running' : 'ready';
}}

function show(data) {{
  document.getElementById('result').textContent = JSON.stringify(data, null, 2);
}}

function payload() {{
  const data = {{}};
  settingsKeys.forEach((key) => {{
    const el = document.getElementById(key);
    data[key] = el ? el.value : '';
  }});
  return data;
}}

function runPayload(dryRun) {{
  const limitEl = document.getElementById('dry_run_limit');
  const data = {{ dry_run: Boolean(dryRun), limit: Number(limitEl?.value || 25) || 25 }};
  exportFlags.forEach((key) => {{
    const el = document.getElementById(key);
    data[key] = el ? Boolean(el.checked) : true;
  }});
  return data;
}}

async function api(path, options = {{}}) {{
  const response = await fetch(path, {{
    cache: 'no-store',
    headers: {{ 'Content-Type': 'application/json', ...(options.headers || {{}}) }},
    ...options,
  }});
  const text = await response.text();
  let data = {{}};
  try {{ data = text ? JSON.parse(text) : {{}}; }} catch (_) {{ data = {{ raw: text }}; }}
  if (!response.ok) throw new Error(`HTTP ${{response.status}} ${{JSON.stringify(data)}}`);
  return data;
}}

async function loadSettings() {{
  setBusy(true);
  try {{
    const data = await api('/api/settings');
    const settings = data.settings || {{}};
    settingsKeys.forEach((key) => {{
      const el = document.getElementById(key);
      if (!el) return;
      if (['client_secret', 'access_token', 'refresh_token', 'webhook_url', 'openrouter_api_key'].includes(key)) return;
      el.value = settings[key] ?? '';
    }});
    show(data);
  }} catch (error) {{
    show({{ ok:false, error:String(error) }});
  }} finally {{
    setBusy(false);
  }}
}}

async function saveSettings() {{
  setBusy(true);
  try {{
    const data = await api('/api/settings', {{ method: 'POST', body: JSON.stringify(payload()) }});
    show(data);
    await loadSettings();
  }} catch (error) {{
    show({{ ok:false, error:String(error) }});
  }} finally {{
    setBusy(false);
  }}
}}

async function runAction(kind) {{
  setBusy(true);
  try {{
    let path = '/api/test';
    let body = null;
    if (kind === 'setup') {{ path = '/api/setup'; body = {{ dry_run:false }}; }}
    if (kind === 'setup-dry') {{ path = '/api/setup'; body = {{ dry_run:true }}; }}
    if (kind === 'dry-run') {{ path = '/api/dry-run'; body = runPayload(true); }}
    if (kind === 'run') {{ path = '/api/run'; body = runPayload(false); }}
    const data = await api(path, {{ method: 'POST', ...(body ? {{ body: JSON.stringify(body) }} : {{}}) }});
    show(data);
  }} catch (error) {{
    show({{ ok:false, error:String(error) }});
  }} finally {{
    setBusy(false);
  }}
}}

document.getElementById('flags').innerHTML = exportFlags.map((key) => `
  <label class="chip"><input id="${{key}}" type="checkbox" checked />${{key.replace('export_', '')}}</label>
`).join('');
loadSettings();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
@app.get("/settings.html", response_class=HTMLResponse)
def ui() -> str:
    return _html()
