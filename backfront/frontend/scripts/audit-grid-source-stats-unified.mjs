import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const api = await readRepo('backfront/frontend/js/script.api.js');
const gridStore = await readRepo('backfront/frontend/js/legacy.grid.store.js');
const gridPage = await readRepo('backfront/frontend/js/react.grid.js');
const dashboardPage = await readRepo('backfront/frontend/js/react.dashboard.js');
const router = await readRepo('backfront/backend/app/routers/leads.py');
const service = await readRepo('backfront/backend/app/services/leads.py');

for (const marker of [
  "const URL_SOURCE_STATS = U('/source-stats')",
  'async function apiGetSourceStats',
  'apiGetSourceStats,',
]) {
  if (!api.includes(marker)) errors.push(`script.api.js missing source-stats API marker: ${marker}`);
}

for (const marker of [
  '/api/payme/sources/runtime-status',
  "buildPagedRequestOptions('grid:runtime-status'",
  'sourceRuntimeToLead(item)',
  'scan_filter: this.ui.scanFilter',
  'status_filter: this.ui.statusFilter',
  'group_filter: this.ui.groupFilter',
  'sort_mode: \'status\'',
]) {
  if (!gridStore.includes(marker)) errors.push(`legacy.grid.store.js must load Grid from runtime-status: ${marker}`);
}

for (const forbidden of [
  'const data = await apiGetLeads({\n            page: this.ui.page',
  'const data = await apiGetSourceStats({',
  "buildPagedRequestOptions('grid:source-stats'",
  'show_bots: false,\n            show_archived: false,\n            scan_filter',
]) {
  if (gridStore.includes(forbidden)) errors.push(`legacy.grid.store.js still has old Grid leads loader marker: ${forbidden}`);
}

for (const marker of [
  'statusFilter',
  'groupFilter',
  'Открыть чат',
  'jsonlDownloadHref',
  'ProgressCell',
  'Лимит времени',
  'Лимит сообщений',
  'read_progress_percent',
]) {
  if (!gridPage.includes(marker)) errors.push(`react.grid.js missing unified Grid marker: ${marker}`);
}

for (const marker of [
  'scannedSources',
  'read_progress_percent',
  'scan_group',
]) {
  if (!dashboardPage.includes(marker)) errors.push(`react.dashboard.js missing matching source stats marker: ${marker}`);
}

for (const marker of [
  'scan_filter: str = Query(default="all")',
  'scan_filter=scan_filter',
]) {
  if (!router.includes(marker)) errors.push(`routers/leads.py missing source-stats scan_filter marker: ${marker}`);
}

for (const marker of [
  'scan_filter: str = Query(default="all")',
  'scan_filter=scan_filter',
  'source_stats:',
]) {
  if (!service.includes(marker)) errors.push(`services/leads.py missing source-stats scan_filter marker: ${marker}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
