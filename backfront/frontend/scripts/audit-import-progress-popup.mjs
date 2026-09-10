import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const storeSource = await readFile(path.join(root, 'js', 'legacy.import.store.js'), 'utf8');
const pageSource = await readFile(path.join(root, 'js', 'react.import.js'), 'utf8');
const errors = [];

if (!/const\s*\{\s*forceFresh\s*=\s*false,\s*progress\s*=\s*false/.test(storeSource)) {
  errors.push('legacy.import.store.js: loadDialogs must be silent by default');
}

if (!/setMembershipFilter\(filterName\)[\s\S]*?progress:\s*true/.test(storeSource) ||
    !storeSource.includes("progressKind: 'filter'")) {
  errors.push('legacy.import.store.js: membership filter buttons must show a short filter progress popup');
}

for (const marker of [
  'syncTelegramImportData()',
  "kind: 'sync-import'",
  'apiPostJson(URL_IMPORT_SYNC_ENABLE',
  'apiPostJson(URL_RELOAD_SOURCE',
  'timeoutMs: 30000',
]) {
  if (!storeSource.includes(marker)) {
    errors.push(`legacy.import.store.js: expected manual sync marker: ${marker}`);
  }
}

for (const marker of [
  'store.syncTelegramImportData()',
  'Синхронизировать',
  'store.saveDialogImportSettings(dialog',
  'store.addDialog(dialog)',
  'store.removeDialog(dialog)',
  'TablePaginationFooter',
  'store.prevPage()',
  'store.nextPage()',
  'store.goToPage(page)',
]) {
  if (!pageSource.includes(marker)) {
    errors.push(`react.import.js: expected import button/action marker: ${marker}`);
  }
}

for (const forbidden of [
  'Обновить список',
  'Выбрать видимые новые',
  'Сбросить выбор',
  'Добавить выбранные',
  'Добавить видимые',
  'Выбрать до',
  'Боты</label>',
  'Архив</label>',
  'store.ui.showBots = e.target.checked',
  'store.ui.showArchived = e.target.checked',
  'Реальное добавление запускает “Добавить выбранные”',
]) {
  if (pageSource.includes(forbidden)) {
    errors.push(`react.import.js: removed import control still present: ${forbidden}`);
  }
}

if (!storeSource.includes('forceFresh: false') || storeSource.includes('forceFresh: hadCachedDialogs')) {
  errors.push('legacy.import.store.js: import page navigation must not force Telegram refresh');
}

for (const marker of [
  "store.ui.showChannels = e.target.checked; store.resetPage();",
  "store.ui.showGroups = e.target.checked; store.resetPage();",
  "store.ui.showPrivate = e.target.checked; store.resetPage();",
]) {
  if (!pageSource.includes(marker)) {
    errors.push(`react.import.js: expected silent type filter reload marker: ${marker}`);
  }
}

if (!pageSource.includes("store.setMembershipFilter('not_added')") ||
    !pageSource.includes("store.setMembershipFilter('added')") ||
    !pageSource.includes("store.setMembershipFilter('all')")) {
  errors.push('react.import.js: membership filter buttons must call setMembershipFilter');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
