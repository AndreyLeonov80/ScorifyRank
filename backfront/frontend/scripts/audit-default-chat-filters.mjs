import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const errors = [];
const storeFiles = [
  'js/legacy.lead.store.js',
  'js/legacy.grid.store.js',
  'js/legacy.import.store.js',
];

function assertDefault(source, file, filterName, expected) {
  const matches = [...source.matchAll(new RegExp(`${filterName}\\s*:\\s*(true|false)`, 'g'))];
  if (!matches.length) {
    errors.push(`${file}: missing ${filterName} default`);
    return;
  }
  const first = matches[0]?.[1];
  if (first !== String(expected)) {
    errors.push(`${file}: ${filterName} must default to ${expected}`);
  }
}

for (const file of storeFiles) {
  const source = await readFile(path.join(root, file), 'utf8');
  assertDefault(source, file, 'showChannels', false);
  assertDefault(source, file, 'showGroups', true);
  assertDefault(source, file, 'showPrivate', false);
  for (const hiddenFilter of ['showBots:', 'showArchived:']) {
    if (source.includes(hiddenFilter)) {
      errors.push(`${file}: source filters must not expose ${hiddenFilter}`);
    }
  }
}

const scriptApi = await readFile(path.join(root, 'js', 'script.api.js'), 'utf8');
for (const marker of [
  'show_groups: params.show_groups !== false',
]) {
  if (!scriptApi.includes(marker)) {
    errors.push(`js/script.api.js: missing enabled-by-default import cache marker ${marker}`);
  }
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
