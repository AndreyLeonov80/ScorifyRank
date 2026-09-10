import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const page = await readRepo('backfront/frontend/js/react.import.js');
const store = await readRepo('backfront/frontend/js/legacy.import.store.js');
const channels = await readRepo('backfront/backend/app/services/channels.py');

for (const marker of [
  'store.syncTelegramImportData()',
  'store.setMembershipFilter(\'not_added\')',
  'store.setMembershipFilter(\'added\')',
  'store.setMembershipFilter(\'all\')',
  'import-filter-active',
  'store.addDialog(dialog)',
  'store.removeDialog(dialog)',
  'store.deleteSelectedDialogs()',
]) {
  if (!page.includes(marker)) errors.push(`react.import.js missing Import action marker: ${marker}`);
}

for (const forbidden of [
  'btn-plus',
  '>+</button>',
  'Создать сделку',
  'Выбрать видимые новые',
  'Добавить выбранные',
  'Добавить видимые',
  'Выбрать до',
  'Обновить список',
  'Боты</label>',
  'Архив</label>',
]) {
  if (page.includes(forbidden)) errors.push(`react.import.js contains forbidden Import control: ${forbidden}`);
}

for (const marker of [
  'setMembershipFilter(filterName)',
  'progressKind: \'filter\'',
  'this.dialogs = []',
  'this.selected = {}',
  'this.resetPage({',
  'forceFresh: false',
]) {
  if (!store.includes(marker)) errors.push(`legacy.import.store.js missing safe filter marker: ${marker}`);
}

if (/setMembershipFilter\(filterName\)[\s\S]{0,1200}forceFresh:\s*true/.test(store)) {
  errors.push('legacy.import.store.js: membership filter must not force Telegram refresh');
}

for (const marker of [
  'api_payme_telegram_dialogs(',
  'membership_filter: str = Query(default="all")',
  'show_channels: bool = Query(default=True)',
  'show_groups: bool = Query(default=True)',
  'show_private: bool = Query(default=True)',
  'return TelegramDialogsPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))',
]) {
  if (!channels.includes(marker)) errors.push(`channels.py missing server-side Import paging/filter marker: ${marker}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
