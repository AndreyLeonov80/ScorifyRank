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
const importPage = await readRepo('backfront/frontend/js/react.import.js');
const gridPage = await readRepo('backfront/frontend/js/react.grid.js');
const channels = await readRepo('backfront/backend/app/services/channels.py');
const leads = await readRepo('backfront/backend/app/services/leads.py');

for (const marker of [
  'page: this.ui.page',
  'page_size: this.ui.pageSize',
  'totalDialogPages',
  'return this.filteredDialogs();',
  'apiGetTelegramDialogs(params',
]) {
  if (!importStore.includes(marker)) errors.push(`legacy.import.store.js missing server paging marker: ${marker}`);
}

for (const marker of [
  'TablePaginationFooter',
  'store.prevPage()',
  'store.nextPage()',
  'store.goToPage(page)',
]) {
  if (!importPage.includes(marker)) errors.push(`react.import.js missing pagination marker: ${marker}`);
}

for (const marker of [
  'page: this.ui.page',
  'page_size: this.ui.pageSize',
  'totalLeadPages',
  'return this.filteredLeads();',
  '/api/payme/sources/runtime-status',
  'buildPagedRequestOptions(\'grid:runtime-status\'',
]) {
  if (!gridStore.includes(marker)) errors.push(`legacy.grid.store.js missing server paging marker: ${marker}`);
}

for (const marker of [
  'TablePaginationFooter',
  'store.prevPage()',
  'store.nextPage()',
  'store.goToPage(page)',
]) {
  if (!gridPage.includes(marker)) errors.push(`react.grid.js missing pagination marker: ${marker}`);
}

for (const marker of [
  'return TelegramDialogsPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))',
  'page_size: int = Query(default=5, ge=1, le=100)',
]) {
  if (!channels.includes(marker)) errors.push(`channels.py missing Import server pagination marker: ${marker}`);
}

for (const marker of [
  'return LeadsPageDTO(**_paginate_items(sorted_items, page=page, page_size=page_size))',
  'return SourceStatsPageDTO(',
  'page_payload = _paginate_items(items, page=page, page_size=page_size)',
]) {
  if (!leads.includes(marker)) errors.push(`leads.py missing Grid/Source server pagination marker: ${marker}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
