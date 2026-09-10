import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const importStore = await readRepo('backfront/frontend/js/legacy.import.store.js');
const gridStore = await readRepo('backfront/frontend/js/legacy.grid.store.js');
const dashboard = await readRepo('backfront/frontend/js/react.dashboard.js');
const channels = await readRepo('backfront/backend/app/services/channels.py');
const leads = await readRepo('backfront/backend/app/services/leads.py');

for (const marker of [
  'await this.loadDialogs({\n          forceFresh: false',
  'syncTelegramImportData()',
  'forceFresh: true',
]) {
  if (!importStore.includes(marker)) errors.push(`legacy.import.store.js missing explicit manual-sync/quiet-open marker: ${marker}`);
}

if (/async init\(\)[\s\S]{0,1200}syncTelegramImportData\(\)/.test(importStore)) {
  errors.push('legacy.import.store.js: init must not start Telegram sync');
}

for (const marker of [
  '/api/payme/sources/runtime-status',
  'buildPagedRequestOptions(\'grid:runtime-status\'',
  'startLeadPolling()',
  'loadTelegramSyncJob()',
  'loadTelegramSyncControl()',
]) {
  if (!gridStore.includes(marker)) errors.push(`legacy.grid.store.js missing light Grid load marker: ${marker}`);
}

if (/async init\(\)[\s\S]{0,1600}apiReloadSource\(/.test(gridStore) ||
    /async init\(\)[\s\S]{0,1600}apiPostJson\(\`\$\{API_BASE\}\/api\/payme\/telegram-sync\/run/.test(gridStore)) {
  errors.push('legacy.grid.store.js: init must not reload sources or start Telegram sync directly');
}

for (const marker of [
  '/api/payme/dashboard/summary-lite',
  'loadFallbackDashboardSummary(50)',
  'window.setInterval',
  'document.hidden',
]) {
  if (!dashboard.includes(marker)) errors.push(`react.dashboard.js missing lightweight dashboard marker: ${marker}`);
}

for (const forbidden of [
  'href="import.html">Import',
  'href="grid.html">Открыть Sync',
  'Обновить сейчас',
]) {
  if (dashboard.includes(forbidden)) errors.push(`react.dashboard.js contains heavy navigation/action marker: ${forbidden}`);
}

const dialogHandler = channels.slice(
  channels.indexOf('async def api_payme_telegram_dialogs('),
  channels.indexOf('async def api_payme_telegram_dialogs_import('),
);
for (const marker of [
  'force_refresh: bool = Query(default=False)',
  'await _get_telegram_dialogs_for_api(force_refresh=bool(force_refresh))',
  'return TelegramDialogsPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))',
]) {
  if (!dialogHandler.includes(marker)) errors.push(`channels.py dialogs handler missing safe marker: ${marker}`);
}
for (const forbidden of ['_schedule_telegram_sync_start', '_ensure_telegram_sync_worker_job', 'telegram_sync.start(']) {
  if (dialogHandler.includes(forbidden)) errors.push(`channels.py dialogs handler must not start heavy work: ${forbidden}`);
}

const sourceStatsHandler = leads.slice(
  leads.indexOf('async def api_payme_source_stats('),
  leads.indexOf('async def api_payme_llm_run('),
);
for (const marker of [
  '_load_leads_for_source_view(',
  '_cached_async_snapshot',
  'SourceStatsPageDTO',
]) {
  if (!sourceStatsHandler.includes(marker)) errors.push(`leads.py source-stats missing cached light marker: ${marker}`);
}
for (const forbidden of ['telegram_sync.start(', '_schedule_duckdb_sync(', '_get_telegram_dialogs_for_api(force_refresh=True)']) {
  if (sourceStatsHandler.includes(forbidden)) errors.push(`leads.py source-stats must not start heavy work: ${forbidden}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
