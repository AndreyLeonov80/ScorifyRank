import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const errors = [];
const apiSource = await readFile(path.join(root, 'js', 'script.api.js'), 'utf8');

for (const marker of [
  'PAGE_UI_STATE_KEY_PREFIX',
  'createPersistedUiState',
  'persistUiState',
  'xfiles.page-ui.',
]) {
  if (!apiSource.includes(marker)) {
    errors.push(`js/script.api.js: missing ${marker}`);
  }
}

for (const [file, key] of [
  ['js/legacy.lead.store.js', 'index.groups-default.v1'],
  ['js/legacy.import.store.js', 'import.groups-default.v1'],
  ['js/legacy.grid.store.js', 'grid.groups-default.v1'],
]) {
  const source = await readFile(path.join(root, file), 'utf8');
  const markers = [
    key,
    'createPersistedUiState(',
    'persistUiState(',
    'pageSize',
    'showChannels',
    'showGroups',
    'showPrivate',
  ];
  for (const marker of markers) {
    if (!source.includes(marker)) {
      errors.push(`${file}: missing ${marker}`);
    }
  }
  if (/createPersistedUiState\([\s\S]*?showBots/.test(source) || /persistUiState\([\s\S]*?showArchived/.test(source)) {
    errors.push(`${file}: UI state must not persist hidden bots/archive filters`);
  }
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
